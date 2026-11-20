"""MQTT -> ClearPath bridge. Subscribes to the sensors' topic and processes each message.

    uv run python -m clearpath.mqtt_bridge

Uses the public broker broker.hivemq.com (the same one configured on the Wokwi ESP32).
A public broker is fine for a demo. In production we would use our own broker with
TLS (port 8883) and a username/password per device.
"""
from __future__ import annotations

import logging

import paho.mqtt.client as mqtt

from . import config, db, iot

logging.basicConfig(level=logging.INFO, format="%(asctime)s [mqtt] %(message)s")
log = logging.getLogger("clearpath.mqtt")


def main():
    con = db.connect()

    def on_connect(client, _userdata, _flags, rc, _props=None):
        log.info("Connected to broker %s (rc=%s). Subscribing to %s", config.MQTT_BROKER, rc, config.MQTT_TOPIC)
        client.subscribe(config.MQTT_TOPIC, qos=1)

    def on_message(_client, _userdata, msg):
        try:
            result = iot.process_message(con, msg.payload)
            log.info("%s -> %s", msg.topic, result)
        except Exception as e:  # a bad message must not bring the bridge down
            log.warning("Message ignored on %s: %s", msg.topic, e)

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="clearpath-bridge")
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(config.MQTT_BROKER, config.MQTT_PORT, keepalive=60)
    client.loop_forever()


if __name__ == "__main__":
    main()
