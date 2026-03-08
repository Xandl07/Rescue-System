import os
import time
import rclpy
from rclpy.node import Node
from std_msgs.msg import Int32
import paho.mqtt.client as mqtt

MQTT_HOST = os.environ.get("MQTT_HOST", "127.0.0.1")  
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_TOPIC_FINAL = os.environ.get("MQTT_TOPIC_FINAL", "rescuesys/box/final")

ROS_TOPIC_CYCLE  = "/current_cycle"
ROS_TOPIC_STATUS = "/final_status"

class Ros2ToMqttBridge(Node):
    def __init__(self):
        super().__init__("ros2_to_mqtt_bridge")

        self.mqtt = mqtt.Client(client_id="ros2_to_mqtt_bridge")
        self.mqtt.on_connect = self.on_mqtt_connect
        self.mqtt.on_disconnect = self.on_mqtt_disconnect

        self.get_logger().info(f"Connecting MQTT broker {MQTT_HOST}:{MQTT_PORT} ...")
        self.mqtt.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
        self.mqtt.loop_start()

        self.last_cycle = None
        self.last_status = None
        self.t_cycle = 0.0
        self.t_status = 0.0

        self.last_published_cycle = None

        self.create_subscription(Int32, ROS_TOPIC_CYCLE,  self.on_cycle,  10)
        self.create_subscription(Int32, ROS_TOPIC_STATUS, self.on_status, 10)

    def on_mqtt_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.get_logger().info("MQTT connected")
        else:
            self.get_logger().error(f"MQTT connect failed rc={rc}")

    def on_mqtt_disconnect(self, client, userdata, rc):
        self.get_logger().warning(f"MQTT disconnected (rc={rc}). Reconnecting...")
        try:
            client.reconnect()
        except Exception as e:
            self.get_logger().error(f"MQTT reconnect failed: {e}")

    def try_publish_final(self):
        if self.last_cycle is None or self.last_status is None:
            return

        max_dt = 2.0
        if abs(self.t_cycle - self.t_status) > max_dt:
            return

        cycle = int(self.last_cycle)
        status = int(self.last_status)

        if self.last_published_cycle == cycle:
            return

        payload = f"{cycle},{status}"
        info = self.mqtt.publish(
            MQTT_TOPIC_FINAL,
            payload=payload,
            qos=1,
            retain=False  
        )

        if info.rc == mqtt.MQTT_ERR_SUCCESS:
            self.last_published_cycle = cycle
            self.get_logger().info(f"MQTT -> {MQTT_TOPIC_FINAL}: {payload}")
        else:
            self.get_logger().error(f"MQTT publish failed rc={info.rc}")

    def on_cycle(self, msg: Int32):
        self.last_cycle = msg.data
        self.t_cycle = time.time()
        self.try_publish_final()

    def on_status(self, msg: Int32):
        self.last_status = msg.data
        self.t_status = time.time()
        self.try_publish_final()

def main():
    rclpy.init()
    node = Ros2ToMqttBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            node.mqtt.loop_stop()
            node.mqtt.disconnect()
        except Exception:
            pass
        node.destroy_node()
        rclpy.shutdown()

if __name__ == "__main__":
    main()