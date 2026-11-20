"""Handling of messages from the "Ramp Sentinel" sensor (ESP32).

The ESP32 sits next to an accessibility ramp with an HC-SR04 ultrasonic sensor
pointing at the front of the ramp. If something (usually a car) stays in front of
it for longer than the limit, it publishes an MQTT event. There is also a button
so that the person with a disability can confirm the blockage themselves.

JSON published on topic clearpath/fiap-gs/sensors/<id>:
{
  "device": "ramp-paulista-01",
  "location": "Ramp at Av. Paulista x R. Augusta",
  "lat": -23.5558, "lon": -46.6623,
  "event": "heartbeat" | "obstruction" | "cleared" | "confirmation",
  "distance_cm": 42.0,
  "duration_s": 35
}
"""
from __future__ import annotations

import json
import sqlite3

from . import db, routing, service

EVENTS = {"heartbeat", "obstruction", "cleared", "confirmation"}


def _open_report(con: sqlite3.Connection, device: str):
    marks = ",".join("?" * len(routing.OPEN_STATUSES))
    return con.execute(
        f"SELECT * FROM reports WHERE device=? AND status IN ({marks}) ORDER BY created_at DESC LIMIT 1",
        (device, *routing.OPEN_STATUSES),
    ).fetchone()


def process_message(con: sqlite3.Connection, payload: dict | str | bytes) -> dict:
    if isinstance(payload, (bytes, str)):
        payload = json.loads(payload)
    device = str(payload.get("device", "")).strip()
    event = payload.get("event")
    if not device or event not in EVENTS:
        raise service.ValidationError(f"Invalid IoT message: device='{device}', event='{event}'")
    dist = payload.get("distance_cm")
    dur = payload.get("duration_s")

    # heartbeat only updates "last seen"; the other events change the ramp state
    state = {"cleared": "clear", "obstruction": "blocked", "confirmation": "blocked"}.get(event)
    with db.transaction(con):
        con.execute(
            "INSERT INTO iot_devices (id, location, lat, lon, last_seen, last_state, distance_cm) "
            "VALUES (?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET location=excluded.location, lat=excluded.lat, "
            "lon=excluded.lon, last_seen=excluded.last_seen, distance_cm=excluded.distance_cm, "
            "last_state=COALESCE(?, iot_devices.last_state)",
            (device, payload.get("location"), payload.get("lat"), payload.get("lon"), db.iso(), state or "clear", dist, state),
        )
        con.execute("INSERT INTO iot_readings (device, at, event, distance_cm, duration_s, raw) VALUES (?,?,?,?,?,?)",
                    (device, db.iso(), event, dist, dur, json.dumps(payload, ensure_ascii=False)))

    open_report = _open_report(con, device)
    if event == "heartbeat":
        return {"action": "heartbeat_recorded"}

    if event == "cleared":
        if open_report:
            with db.transaction(con):
                con.execute("INSERT INTO history (protocol, at, status, note) VALUES (?,?,?,?)",
                            (open_report["protocol"], db.iso(), open_report["status"],
                             "Sensor reports the ramp is clear (awaiting confirmation from the agency)"))
        return {"action": "clearance_recorded", "protocol": open_report["protocol"] if open_report else None}

    if open_report:
        bonus = 15 if event == "confirmation" else 5
        points = min(100, open_report["urgency_points"] + bonus)
        priority = routing.priority_from_points(points)
        note = ("A citizen confirmed the blockage with the sensor's button" if event == "confirmation"
                else f"New detection: blocked for {dur} s")
        with db.transaction(con):
            con.execute("UPDATE reports SET urgency_points=?, priority=?, updated_at=? WHERE protocol=?",
                        (points, priority, db.iso(), open_report["protocol"]))
            con.execute("INSERT INTO history (protocol, at, status, note) VALUES (?,?,?,?)",
                        (open_report["protocol"], db.iso(), open_report["status"], note))
        return {"action": "report_reinforced", "protocol": open_report["protocol"], "priority": priority}

    if event == "confirmation":
        text = (f"A person with a disability pressed the sensor's help button reporting that the ramp is blocked "
                f"at {payload.get('location', device)}. I cannot get through.")
    else:
        text = (f"Sensor detected an obstruction in front of the accessibility ramp at {payload.get('location', device)} "
                f"for {dur} seconds (object at {dist} cm).")
    report = service.process_report(con, text, payload.get("lat"), payload.get("lon"),
                                    source="iot", forced_category="sidewalk_obstruction", device=device)
    return {"action": "report_created", "protocol": report["protocol"], "priority": report["priority"]}
