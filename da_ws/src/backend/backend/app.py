from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

import os, glob, io, tempfile, threading, time
import serial
from PIL import Image, ImageOps

from pathlib import Path
import json

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],     
    allow_methods=["*"],
    allow_headers=["*"],
)

SERIAL_PORT = "/dev/matrixportal-data"
BAUD = 115200

STATE_PATH = Path(os.environ.get(
    "RESCUEBOX_STATE_PATH",
    f"/home/{os.environ.get('USER','rescue-pi')}/.rescuebox/state.json"
))

def find_circuitpy():
    candidates = ["/media/CIRCUITPY"]

    user = os.environ.get("USER", "rescue-pi")
    candidates += [
        f"/media/{user}/CIRCUITPY",
        "/mnt/CIRCUITPY",
    ]

    candidates += glob.glob("/media/*/CIRCUITPY")

    for p in candidates:
        try:
            if os.path.isdir(p) and os.path.exists(os.path.join(p, "boot_out.txt")):
                return p
        except Exception:
            pass
    return None

def get_custom_bmp_path():
    mnt = find_circuitpy()
    if not mnt:
        return None
    return os.path.join(mnt, "custom.bmp")

def image_to_custom_bmp_bytes(image_bytes: bytes) -> bytes:
    im = Image.open(io.BytesIO(image_bytes))
    im = ImageOps.exif_transpose(im)
    im = im.convert("RGB")

    target_w, target_h = 64, 32

    im.thumbnail((target_w, target_h), Image.Resampling.LANCZOS)

    canvas = Image.new("RGB", (target_w, target_h), (0, 0, 0))
    x = (target_w - im.size[0]) // 2
    y = (target_h - im.size[1]) // 2
    canvas.paste(im, (x, y))

    pal = canvas.convert(
        "P",
        palette=Image.Palette.ADAPTIVE,
        colors=256,
        dither=Image.Dither.NONE
    )

    out = io.BytesIO()
    pal.save(out, format="BMP", bits=8, compress=False, bmp_version=3)
    return out.getvalue()

def write_atomic(path: str, data: bytes):
    d = os.path.dirname(path) or "."
    with tempfile.NamedTemporaryFile("wb", delete=False, dir=d) as tf:
        tf.write(data)
        tf.flush()
        os.fsync(tf.fileno())
        tmp = tf.name
    os.replace(tmp, path)
    try:
        os.sync()
    except Exception:
        pass

def send_mode_custom_with_retries(total_s=10.0, interval_s=0.4):
    deadline = time.monotonic() + total_s
    ok_any = False
    while time.monotonic() < deadline:
        ok_any = serial_send("MODE:CUSTOM") or ok_any
        time.sleep(interval_s)
    return ok_any

_ser = None
_lock = threading.Lock()

def _connect_loop():
    global _ser
    while True:
        if _ser is None:
            try:
                s = serial.Serial(SERIAL_PORT, BAUD, timeout=0.2, write_timeout=0.2)
                s.dtr = False
                s.rts = False
                with _lock:
                    _ser = s
                print(f"[serial] connected: {SERIAL_PORT}")
            except Exception as e:
                print(f"[serial] connect failed: {e}")
                time.sleep(1.0)
        time.sleep(0.2)

threading.Thread(target=_connect_loop, daemon=True).start()

def serial_send(line: str) -> bool:
    global _ser
    data = (line.strip() + "\n").encode("utf-8")
    with _lock:
        s = _ser
    if not s:
        return False
    try:
        s.write(data)
        s.flush()
        return True
    except Exception as e:
        print(f"[serial] write failed: {e}")
        with _lock:
            try:
                _ser.close()
            except Exception:
                pass
            _ser = None
        return False

def load_assessment_state():
    try:
        if not STATE_PATH.exists():
            return {"updatedAt": None, "cycles": {}}
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        return {"updatedAt": None, "cycles": {}, "error": str(e)}

def save_assessment_state_atomic(state: dict):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, STATE_PATH)

@app.post("/upload_image")
async def upload_image(file: UploadFile = File(...)):
    custom_path = get_custom_bmp_path()
    if not custom_path:
        return JSONResponse({"status": "error", "detail": "CIRCUITPY nicht gemountet"}, status_code=500)

    image_bytes = await file.read()
    if not image_bytes:
        return JSONResponse({"status": "error", "detail": "Leere Datei"}, status_code=400)

    bmp = image_to_custom_bmp_bytes(image_bytes)
    write_atomic(custom_path, bmp)

    ok = serial_send("MODE:CUSTOM")
    return {"status": "ok", "detail": "custom.bmp gespeichert; MODE:CUSTOM gesendet", "serial_sent": ok}

@app.get("/set_mode/{mode}")
def set_mode(mode: str, message: str | None = None):
    m = mode.lower()

    if m == "ambu":
        ok = serial_send("MODE:AMBU")
        return {"status": "ok", "mode": "ambu", "serial_sent": ok}

    if m == "nothing":
        ok = serial_send("MODE:NOTHING")
        return {"status": "ok", "mode": "nothing", "serial_sent": ok}

    if m == "party":
        ok = serial_send("MODE:PARTY")
        return {"status": "ok", "mode": "party", "serial_sent": ok}

    if m == "text":
        ok = serial_send(f"TEXT:{message or ''}")
        return {"status": "ok", "mode": "text", "serial_sent": ok}

    if m == "custom":
        ok = serial_send("MODE:CUSTOM")
        return {"status": "ok", "mode": "custom", "serial_sent": ok}

    return JSONResponse({"status": "error", "detail": "unknown mode"}, status_code=400)

@app.get("/api/assessment/state")
def get_assessment_state():
    data = load_assessment_state()
    return JSONResponse(data, headers={"Cache-Control": "no-store"})

@app.post("/api/assessment/reset")
def reset_assessment_state():
    state = {
        "updatedAt": time.time(),
        "cycles": {
            "1": {"lines": {}, "lastStatus": "unknown", "total": 15},
            "2": {"lines": {}, "lastStatus": "unknown", "total": 15},
            "3": {"lines": {}, "lastStatus": "unknown", "total": 15},
            "4": {"lines": {}, "lastStatus": "unknown", "total": 15},
        }
    }
    save_assessment_state_atomic(state)
    return {"ok": True}

