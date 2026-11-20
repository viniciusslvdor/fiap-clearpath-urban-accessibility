# IoT: Ramp Sentinel (ESP32 + MQTT + Node-RED)

## What it does

An ESP32 with an HC-SR04 ultrasonic sensor sits next to an accessibility ramp, pointing at the front of it.

| Situation | What the ESP32 does |
|---|---|
| Something closer than 80 cm for 10 s in a row (in the demo; 60 s in the field) | Red LED, 1 beep, publishes `obstruction` |
| Clear (more than 100 cm) for 5 s | Green LED, publishes `cleared` |
| Blue button pressed | 2 beeps ("received"), publishes `confirmation` |
| Every 60 s | publishes `heartbeat` (shows the sensor is alive) |

The **median of 5 readings** filters false echoes, and the **state machine** with a minimum time avoids firing for pedestrians or passing cars.
The **hysteresis** (80 cm to block, 100 cm to clear) avoids flickering around the threshold.

Topic: `clearpath/fiap-gs/sensors/ramp-paulista-01` · Broker: `broker.hivemq.com:1883`

```json
{"device":"ramp-paulista-01","location":"Ramp at Av. Paulista x R. Augusta","lat":-23.5558,"lon":-46.6623,
 "event":"obstruction","distance_cm":46.8,"duration_s":10}
```

## Circuit

| Component | ESP32 pin |
|---|---|
| HC-SR04 TRIG / ECHO | GPIO 5 / GPIO 18 (VCC on 5V) |
| Button (INPUT_PULLUP) | GPIO 4 and GND |
| Red LED + 220 Ω | GPIO 26 |
| Green LED + 220 Ω | GPIO 27 |
| Buzzer | GPIO 25 |

## How to simulate on Wokwi

Project already created: https://wokwi.com/projects/481174110278029313 (open it and click ▶).

To build it from scratch:

1. Go to https://wokwi.com/projects/new/esp32.
2. Replace the content of `sketch.ino` and `diagram.json` with the files in `wokwi/`.
3. Create the `libraries.txt` file ("Library Manager" tab → "+") with `PubSubClient` and `ArduinoJson`.
4. Click ▶. The Serial Monitor shows the Wi-Fi connection and every MQTT message published.
5. Click the HC-SR04 sensor and drag the distance below 80 cm. After 10 s the LED turns red and the `obstruction` event is sent.
6. Click the blue button to send `confirmation`. Move the distance back above 100 cm for `cleared`.

For the event to become a report in the system, keep the MQTT bridge running on the computer (`uv run python -m clearpath.mqtt_bridge`, see the main README).

> ⚠️ **Test status:** the firmware has **not been run on Wokwi yet**. It must be run and the evidence recorded (screenshot of the Serial Monitor and the LEDs) before submission. If something fails, fix it and only then describe it as working in the report.
>
> Without Wokwi open, `uv run python scripts/simulate_sensor.py` publishes the same sequence of messages. This path was tested: the public broker delivered the 4 messages and the bridge created the report, reinforced it and recorded the clearance.

## Node-RED (sensor dashboard)

1. `npm install -g node-red` and then `node-red`. Open http://localhost:1880.
2. Menu → Manage palette → Install → `node-red-dashboard`.
3. Menu → Import → select `node-red/clearpath_flow.json` → Deploy.
4. Dashboard at http://localhost:1880/ui: ramp state, distance gauge, history and obstruction counter.

## Limitations

- Public broker without TLS: anyone can publish to the topic. In production: own broker, TLS (8883) and per-device credentials.
- Ultrasound cannot tell a car from a dumpster or a person standing still; the minimum time reduces, but does not eliminate, false positives.
- Power supply and protection against rain and vandalism were not addressed in the prototype.
