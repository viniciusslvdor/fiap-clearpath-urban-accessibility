"""End-to-end tests: REST API -> anonymization -> NLP -> vision -> routing -> automation."""
from datetime import datetime, timedelta

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

import generate_demo_images as gen
from clearpath import config, db, routing, service
from clearpath.api import app, con

client = TestClient(app)


def submit(text, lat=None, lon=None, photo=None, consent=True):
    data = {"text": text, "consent": str(consent).lower()}
    if lat is not None:
        data.update(lat=str(lat), lon=str(lon))
    files = {"photo": ("photo.jpg", photo, "image/jpeg")} if photo else None
    return client.post("/api/reports", data=data, files=files)


def jpg(level, seed):
    return cv2.imencode(".jpg", gen.generate(level, np.random.default_rng(seed)))[1].tobytes()


def test_health():
    r = client.get("/api/health").json()
    assert r["status"] == "ok" and r["nlp_model"] is True


def test_consent_is_required():
    assert submit("broken sidewalk on my street", consent=False).status_code == 400


def test_short_text_is_rejected():
    assert submit("hi").status_code == 422


def test_full_flow_with_photo_and_personal_data():
    r = submit("Huge hole in the sidewalk on Rua Vergueiro, 900, my elderly father fell. cpf 111.222.333-44",
               -23.5801234, -46.6401234, jpg("severe", 3))
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["protocol"].startswith("CP-")
    assert d["category"] == "damaged_sidewalk"
    assert "[CPF]" in d["anonymized_text"] and "111.222" not in d["anonymized_text"]
    assert d["personal_data_removed"] == {"CPF": 1}
    assert d["lat"] == -23.5801
    assert d["image_analysis"]["level"] == "severe"
    assert d["priority"] == "critical"
    assert d["status"] == "forwarded"
    assert d["agency"].startswith("Subprefecture")
    assert [h["status"] for h in d["history"]] == ["received", "forwarded"]
    assert (config.LETTERS_DIR / f"{d['protocol']}_forwarding.eml").exists()
    assert (config.MEDIA_DIR / d["photo_analysis"]).exists()
    assert "text_hash" not in d

    assert client.get(f"/api/reports/{d['protocol']}").json()["status"] == "forwarded"


def test_same_text_again_returns_same_protocol():
    a = submit("the traffic light at the school corner is off").json()
    b = submit("the traffic light at the school corner is off").json()
    assert a["protocol"] == b["protocol"] and b["duplicate"] is True


def test_groups_reports_about_the_same_barrier():
    a = submit("there is no ramp at all at this corner", -23.5000, -46.6000).json()
    b = submit("missing access ramp here, wheelchair users cannot get up", -23.50015, -46.60012).json()
    c = submit("missing access ramp at the other corner of the neighborhood", -23.5100, -46.6000).json()
    assert b["group_root"] == a["protocol"]
    assert c["group_root"] is None
    root = client.get(f"/api/reports/{a['protocol']}").json()
    assert root["urgency_points"] > a["urgency_points"]
    assert "New report about the same barrier" in root["history"][-1]["note"]


def test_ambiguous_text_goes_to_human_triage():
    d = submit("I don't really know how to explain it, there is a problem around here").json()
    assert d["status"] == "human_triage"
    assert not (config.LETTERS_DIR / f"{d['protocol']}_forwarding.eml").exists()


def test_agency_status_update():
    p = submit("pedestrian crossing completely faded on the avenue").json()["protocol"]
    assert client.patch(f"/api/reports/{p}/status", json={"status": "nonexistent"}).status_code == 422
    r = client.patch(f"/api/reports/{p}/status", json={"status": "resolved", "note": "crosswalk repainted"})
    assert r.json()["status"] == "resolved"


def test_robot_escalates_missed_deadline():
    p = submit("the train station elevator is out of order").json()["protocol"]
    deadline = con.execute("SELECT deadline FROM reports WHERE protocol=?", (p,)).fetchone()["deadline"]
    later = datetime.fromisoformat(deadline) + timedelta(days=1)
    escalated = routing.escalate_overdue(con, later)
    assert p in escalated
    assert client.get(f"/api/reports/{p}").json()["status"] == "escalated"
    assert (config.LETTERS_DIR / f"{p}_escalation.eml").exists()


def test_right_to_erasure():
    d = submit("cracked sidewalk near the neighborhood bakery", photo=jpg("moderate", 9)).json()
    assert client.delete(f"/api/reports/{d['protocol']}/data").status_code == 200
    r = client.get(f"/api/reports/{d['protocol']}").json()
    assert r["photo"] is None and r["anonymized_text"].startswith("[removed")
    assert not (config.MEDIA_DIR / d["photo"]).exists()
    actions = [a["action"] for a in con.execute("SELECT action FROM audit_log WHERE protocol=?", (d["protocol"],))]
    assert actions == ["report_collected", "erasure_on_request"]


@pytest.mark.parametrize("event", ["flying"])
def test_iot_rejects_invalid_event(event):
    assert client.post("/api/iot/readings", json={"device": "x", "event": event}).status_code == 422


def test_iot_obstruction_confirmation_clearance():
    base = {"device": "ramp-test-01", "location": "Test ramp", "lat": -23.4, "lon": -46.4}
    r1 = client.post("/api/iot/readings", json={**base, "event": "obstruction", "distance_cm": 50, "duration_s": 31}).json()
    assert r1["action"] == "report_created"
    rep = client.get(f"/api/reports/{r1['protocol']}").json()
    assert rep["source"] == "iot" and rep["category"] == "sidewalk_obstruction" and rep["status"] == "forwarded"

    r2 = client.post("/api/iot/readings", json={**base, "event": "confirmation", "distance_cm": 49}).json()
    assert r2 == {"action": "report_reinforced", "protocol": r1["protocol"], "priority": r2["priority"]}
    assert client.get(f"/api/reports/{r1['protocol']}").json()["urgency_points"] > rep["urgency_points"]

    r3 = client.post("/api/iot/readings", json={**base, "event": "cleared", "distance_cm": 300}).json()
    assert r3["action"] == "clearance_recorded"
    dev = {d["id"]: d for d in client.get("/api/iot/devices").json()}["ramp-test-01"]
    assert dev["last_state"] == "clear" and len(dev["readings"]) == 3


def test_retention_deletes_photos_of_old_resolved_reports():
    d = submit("sidewalk with big cracks near the market", photo=jpg("moderate", 11)).json()
    client.patch(f"/api/reports/{d['protocol']}/status", json={"status": "resolved"})
    assert d["protocol"] not in service.apply_retention(con)
    in_91_days = db.now() + timedelta(days=config.PHOTO_RETENTION_DAYS + 1)
    assert d["protocol"] in service.apply_retention(con, in_91_days)
    assert client.get(f"/api/reports/{d['protocol']}").json()["photo"] is None
    assert not (config.MEDIA_DIR / d["photo"]).exists()


def test_indicators():
    d = client.get("/api/indicators").json()
    assert d["total_reports"] >= 5
    assert d["reports_with_personal_data_removed"] >= 1
    assert len(d["last_30_days"]) == 30
    assert sum(d["by_priority"].values()) == d["total_reports"]
