import time
import gpiod
import rclpy
from rclpy.node import Node
from std_msgs.msg import Int32

class LinearActuatorPulseRetract(Node):

    def __init__(self):
        super().__init__("linear_actuator")

        self.GPIOCHIP = "gpiochip4"  
        self.IN1_LINE = 23            
        self.IN2_LINE = 24            

        self.T_RETRACT_PULSE = 4.5

        self.T_PAUSE = 0.2

        self.extend_cmd = (True, False)   
        self.retract_cmd = (False, True) 
        self.stop_cmd = (False, False)    

        self.chip = gpiod.Chip(self.GPIOCHIP)
        self.in1 = self.chip.get_line(self.IN1_LINE)
        self.in2 = self.chip.get_line(self.IN2_LINE)

        self.in1.request(consumer="actuator", type=gpiod.LINE_REQ_DIR_OUT, default_val=0)
        self.in2.request(consumer="actuator", type=gpiod.LINE_REQ_DIR_OUT, default_val=0)

        self.state = "EXTENDED_DEFAULT"
        self.deadline = 0.0

        self.sub = self.create_subscription(
            Int32,
            "/final_status",
            self.on_trigger,
            10
        )

        self.timer = self.create_timer(0.05, self.tick)

        self.set_outputs(*self.extend_cmd)
        self.get_logger().info("Ready")

    def set_outputs(self, in1_high: bool, in2_high: bool):
        if in1_high and in2_high:
            in1_high = in2_high = False
        self.in1.set_value(1 if in1_high else 0)
        self.in2.set_value(1 if in2_high else 0)

    def on_trigger(self, msg: Int32):
        self.get_logger().info(f"Trigger received: {msg.data}")

        if self.state != "EXTENDED_DEFAULT":
            self.get_logger().warn("Busy -> trigger ignored")
            return

        self.get_logger().info("Trigger -> RETRACT pulse")
        self.state = "RETRACTING_PULSE"
        self.deadline = time.monotonic() + self.T_RETRACT_PULSE
        self.set_outputs(*self.retract_cmd)

    def tick(self):
        now = time.monotonic()

        if self.state == "RETRACTING_PULSE" and now >= self.deadline:
            self.state = "PAUSE"
            self.deadline = now + self.T_PAUSE
            self.set_outputs(*self.stop_cmd)

        elif self.state == "PAUSE" and now >= self.deadline:
            self.state = "EXTENDED_DEFAULT"
            self.set_outputs(*self.extend_cmd)
            self.get_logger().info("Back to EXTEND default")

    def destroy_node(self):
        try:
            self.set_outputs(*self.stop_cmd)
            self.in1.release()
            self.in2.release()
            self.chip.close()
        except Exception:
            pass
        super().destroy_node()

def main():
    rclpy.init()
    node = LinearActuatorPulseRetract()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.shutdown()

if __name__ == "__main__":
    main()
