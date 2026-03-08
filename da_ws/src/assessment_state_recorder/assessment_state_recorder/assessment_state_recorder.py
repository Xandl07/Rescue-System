import os
import re
import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Int32

LINE_RE = re.compile(
    r"^cycle:\s*(\d+)\s+\[(\d+)\s*/\s*(\d+)\]\s+(.+?)\s+(?:→|->)\s+(.+?)\s+\(Status:\s*([^)]+)\)\s*$",
    re.IGNORECASE,
)

def default_state(total: int = 15) -> Dict[str, Any]:
    return {
        "updatedAt": None,
        "cycles": {
            "1": {"lines": {}, "lastStatus": "unknown", "total": total},
            "2": {"lines": {}, "lastStatus": "unknown", "total": total},
            "3": {"lines": {}, "lastStatus": "unknown", "total": total},
            "4": {"lines": {}, "lastStatus": "unknown", "total": total},
        },
    }

class AssessmentStateRecorder(Node):
    def __init__(self) -> None:
        super().__init__("assessment_state_recorder")

        default_path = f"/home/{os.environ.get('USER','rescue-pi')}/.rescuebox/state.json"
        self.state_path = Path(os.environ.get("RESCUEBOX_STATE_PATH", default_path))

        self.state_path.parent.mkdir(parents=True, exist_ok=True)

        self.state: Dict[str, Any] = self._load_state_or_default()

        self._dirty = False
        self._last_write = 0.0
        self._min_write_interval_s = float(os.environ.get("RESCUEBOX_MIN_WRITE_INTERVAL", "0.25"))
        self._flush_timer = self.create_timer(0.2, self._flush_if_needed)

        self.sub = self.create_subscription(String, "/assessment_protocol", self._on_msg, 10)

        self.last_cycle = 1
        self._pending_final = None         
        self._pending_window_s = 2.0 

        self.sub_cycle = self.create_subscription(
            Int32, "/current_cycle", self._on_current_cycle, 10
        )

        self.sub_final = self.create_subscription(
            Int32, "/final_status", self._on_final_status, 10
        )

        self.get_logger().info(f"Recording /assessment_protocol -> {self.state_path}")

    def _load_state_or_default(self) -> Dict[str, Any]:
        if self.state_path.exists():
            try:
                data = json.loads(self.state_path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and "cycles" in data:
                    return data
            except Exception as e:
                self.get_logger().warn(f"Failed to read existing state.json, starting fresh: {e}")

        return default_state()

    def _reset_all(self, total: int = 15) -> None:
        self.state = default_state(total=total)
        self.get_logger().info("Reset all cycles (new deployment).")
        self._mark_dirty()

    def _mark_dirty(self) -> None:
        self._dirty = True
        self.state["updatedAt"] = time.time()

    def _write_state_atomic(self) -> None:
        tmp = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.state, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.state_path)

    def _flush_if_needed(self) -> None:
        if not self._dirty:
            return
        now = time.time()
        if now - self._last_write < self._min_write_interval_s:
            return
        try:
            self._write_state_atomic()
            self._dirty = False
            self._last_write = now
        except Exception as e:
            self.get_logger().error(f"Failed writing state: {e}")

    def _on_current_cycle(self, msg: Int32) -> None:
        try:
            self.last_cycle = int(msg.data)
        except Exception:
            self.last_cycle = 1

        self._try_apply_pending_final()
    
    def _on_final_status(self, msg: Int32) -> None:
        s = int(msg.data)

        self._pending_final = (s, time.time())
        self._try_apply_pending_final()

    def _try_apply_pending_final(self) -> None:
        if not self._pending_final:
            return

        s, t0 = self._pending_final

        if time.time() - t0 > self._pending_window_s:
            self._pending_final = None
            return

        if s == 0:
            status = "ok"
        elif s == 1:
            status = "bad"
        else:
            status = "critical"

        cycle_key = str(self.last_cycle)
        if "cycles" not in self.state or cycle_key not in self.state["cycles"]:
            return

        cstate = self.state["cycles"][cycle_key]

        cstate["finalStatusInt"] = s
        cstate["finalStatus"] = status
        cstate["finishedAt"] = time.time()

        lines = cstate.get("lines", {})
        try:
            max_idx = max((int(k) for k in lines.keys()), default=0)
        except Exception:
            max_idx = 0

        lines[str(max_idx + 1)] = f"Abfrage beendet (Status: {status})"
        cstate["lines"] = lines
        cstate["total"] = max(cstate.get("total", 15), max_idx + 1)
        cstate["lastStatus"] = status

        self._mark_dirty()

        self._pending_final = None


    def _parse_line(self, line: str) -> Optional[Dict[str, Any]]:
        if not line:
            return None
        line = line.replace("\r", "").strip()
        m = LINE_RE.match(line)
        if not m:
            return None

        return {
            "cycle": int(m.group(1)),
            "index": int(m.group(2)),
            "total": int(m.group(3)),
            "question": m.group(4).strip(),
            "answer": m.group(5).strip(),
            "status": m.group(6).strip().lower(),
        }

    def _on_msg(self, msg: String) -> None:
        parsed = self._parse_line(msg.data)
        if not parsed:
            return

        cycle = parsed["cycle"]
        idx = parsed["index"]
        total = parsed["total"]
        status = parsed["status"]
        question = parsed["question"]
        answer = parsed["answer"]

        if str(cycle) not in self.state.get("cycles", {}):
            return

        if cycle == 1 and idx == 1:
            self._reset_all(total=total)

        cstate = self.state["cycles"][str(cycle)]

        if idx == 1:
            cstate["lines"] = {}
            cstate["total"] = total
            cstate["lastStatus"] = "unknown"

        cstate["lines"][str(idx)] = f"{idx}. {question}\n→ {answer}"
        cstate["total"] = total
        cstate["lastStatus"] = status

        self._mark_dirty()

def main() -> None:
    rclpy.init()
    node = AssessmentStateRecorder()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
