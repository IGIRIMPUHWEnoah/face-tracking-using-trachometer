# src/mqtt_controller.py
"""
MQTT Client for publishing face tracking signals over Wi-Fi.

Broker Options:
  - Public free broker: "broker.hivemq.com" or "broker.emqx.io" (Port 1883)
  - Local broker: "localhost" or local IP address (e.g. 192.168.1.100)

Topic: "robot/facetracking/position"
Payload (JSON):
  {
    "norm_x": 0.45,
    "offset_x": 144.0,
    "speed_x": 12.5,
    "target_step": 230
  }
"""
from __future__ import annotations

import json
import time
from typing import Optional

try:
    import paho.mqtt.client as mqtt
    HAS_PAHO_MQTT = True
except ImportError:
    mqtt = None
    HAS_PAHO_MQTT = False


class MQTTController:
    """
    Manages MQTT connection and publishes real-time tracking signals.
    """

    def __init__(
        self,
        broker: str = "broker.hivemq.com",
        port: int = 1883,
        topic: str = "robot/facetracking/position",
        client_id: str = "python_face_tracker",
        min_send_interval_s: float = 0.04,  # 25 Hz max publish rate
    ):
        self.broker = broker
        self.port = port
        self.topic = topic
        self.client_id = client_id
        self.min_send_interval_s = min_send_interval_s
        self.client: Optional[mqtt.Client] = None
        self.connected = False
        self.last_send_time = 0.0

        if not HAS_PAHO_MQTT:
            print("[MQTTController] Warning: paho-mqtt not installed. SIMULATION mode active.")

    def connect(self) -> bool:
        if not HAS_PAHO_MQTT:
            return False

        try:
            print(f"[MQTTController] Connecting to MQTT broker '{self.broker}:{self.port}'...")
            if hasattr(mqtt, "CallbackAPIVersion"):
                self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"{self.client_id}_{int(time.time())}")
            else:
                self.client = mqtt.Client(client_id=f"{self.client_id}_{int(time.time())}")
            
            def on_connect(client, userdata, flags, rc, properties=None):
                if rc == 0:
                    self.connected = True
                    print(f"[MQTTController] Connected to MQTT broker '{self.broker}'. Topic: '{self.topic}'")
                else:
                    self.connected = False
                    print(f"[MQTTController] Connection failed with code {rc}")

            def on_disconnect(client, userdata, rc, properties=None):
                self.connected = False
                print("[MQTTController] Disconnected from MQTT broker.")

            self.client.on_connect = on_connect
            self.client.on_disconnect = on_disconnect

            self.client.connect(self.broker, self.port, keepalive=60)
            self.client.loop_start()

            # Wait briefly for connection confirmation
            time.sleep(1.0)
            return self.connected
        except Exception as e:
            print(f"[MQTTController] Error connecting to MQTT broker: {e}")
            self.connected = False
            return False

    def publish_position(self, norm_x: float, offset_x: float = 0.0, speed_x: float = 0.0) -> bool:
        """
        Publishes normalized position norm_x in range [-1.0, +1.0].
        """
        now = time.time()
        if now - self.last_send_time < self.min_send_interval_s:
            return False  # Throttle high-frequency updates

        norm_x = max(-1.0, min(1.0, float(norm_x)))
        target_step = int(norm_x * 1024)  # Match firmware MAX_SWEEP_STEPS = 1024

        payload = {
            "norm_x": round(norm_x, 3),
            "offset_x": round(offset_x, 1),
            "speed_x": round(speed_x, 1),
            "target_step": target_step,
            "timestamp": int(now * 1000),
        }

        json_str = json.dumps(payload)

        if self.connected and self.client:
            try:
                res = self.client.publish(self.topic, json_str, qos=0)
                self.last_send_time = now
                return res.rc == mqtt.MQTT_ERR_SUCCESS
            except Exception as e:
                print(f"[MQTTController] Publish error: {e}")
                return False
        else:
            self.last_send_time = now
            return True

    def close(self):
        if self.client:
            try:
                self.client.loop_stop()
                self.client.disconnect()
            except Exception:
                pass
        self.connected = False


def main():
    print("=== Testing MQTTController ===")
    mc = MQTTController(broker="broker.hivemq.com")
    mc.connect()

    print("Publishing test sweep signals [-1.0 -> 0.0 -> +1.0]...")
    for val in [-1.0, -0.5, 0.0, 0.5, 1.0, 0.0]:
        print(f"Publishing norm_x: {val}")
        mc.publish_position(val)
        time.sleep(0.5)

    mc.close()
    print("Test complete.")


if __name__ == "__main__":
    main()
