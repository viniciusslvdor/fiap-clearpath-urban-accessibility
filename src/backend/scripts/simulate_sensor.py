"""Simulates the ESP32 publishing to the MQTT broker (useful without Wokwi open)."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import paho.mqtt.client as mqtt

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from clearpath import config  # noqa: E402

BASE = {"device": "ramp-simulated-99", "location": "Simulated ramp (script)", "lat": -23.5612, "lon": -46.6559}
TOPIC = config.MQTT_TOPIC.replace("#", BASE["device"])

SEQUENCE = [
    {"event": "heartbeat", "distance_cm": 305.2},
    {"event": "obstruction", "distance_cm": 46.8, "duration_s": 10},
    {"event": "confirmation", "distance_cm": 47.1},
    {"event": "cleared", "distance_cm": 298.4},
]


def main(interval: float = 2.0):
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="clearpath-simulator")
    client.connect(config.MQTT_BROKER, config.MQTT_PORT, keepalive=30)
    client.loop_start()
    for step in SEQUENCE:
        msg = json.dumps({**BASE, **step})
        info = client.publish(TOPIC, msg, qos=1)
        info.wait_for_publish(timeout=10)
        print(f"published on {TOPIC}: {msg}")
        time.sleep(interval)
    client.loop_stop()
    client.disconnect()


if __name__ == "__main__":
    main()
