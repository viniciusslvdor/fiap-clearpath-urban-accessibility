"""Process automation for routing (the "robot" that replaces manual triage).

Automated flow (see docs/architecture.md, simplified BPMN diagram):
  received -> [classify, prioritize, group] -> forwarded (generates an .eml letter to the agency)
  -> in_progress -> resolved
  If the deadline (SLA) expires without resolution: escalated (letter to the Ombudsman).
  If the classifier's confidence is low: human_triage (not forwarded automatically).
"""
from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timedelta
from email.message import EmailMessage
from functools import lru_cache
from pathlib import Path

from . import config, db
from .nlp import CATEGORIES

VALID_STATUSES = ["received", "human_triage", "forwarded", "in_progress", "resolved", "escalated"]
OPEN_STATUSES = ("received", "human_triage", "forwarded", "in_progress", "escalated")


@lru_cache(maxsize=1)
def agencies() -> dict:
    return json.loads(config.AGENCIES_FILE.read_text(encoding="utf-8"))


def priority_from_points(points: int) -> str:
    if points >= 75:
        return "critical"
    if points >= 55:
        return "high"
    if points >= 35:
        return "medium"
    return "low"


def vision_bonus(damage_level: str | None) -> int:
    return {"severe": 20, "moderate": 10}.get(damage_level or "", 0)


def distance_m(lat1, lon1, lat2, lon2) -> float:
    """Haversine formula."""
    r = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def find_group(con: sqlite3.Connection, category: str, lat, lon) -> tuple[str | None, int]:
    """Open reports of the same category less than GROUPING_RADIUS_M meters away are the same barrier.
    Returns (root protocol, number of reports already in the group)."""
    if lat is None or lon is None:
        return None, 0
    marks = ",".join("?" * len(OPEN_STATUSES))
    rows = con.execute(
        f"SELECT protocol, group_root, lat, lon FROM reports WHERE category=? AND lat IS NOT NULL "
        f"AND status IN ({marks}) ORDER BY created_at",
        (category, *OPEN_STATUSES),
    ).fetchall()
    nearby = [r for r in rows if distance_m(lat, lon, r["lat"], r["lon"]) <= config.GROUPING_RADIUS_M]
    if not nearby:
        return None, 0
    root = nearby[0]["group_root"] or nearby[0]["protocol"]
    return root, len(nearby)


def compute_deadline(priority: str, start: datetime | None = None) -> datetime:
    days = agencies()["sla_days"][priority]
    return (start or db.now()) + timedelta(days=days)


def write_letter(report: dict, recipient: dict, subject: str, extra_body: str = "") -> Path:
    """Generates an .eml message ready to be sent (simulated: it stays in the outbox folder)."""
    config.ensure_dirs()
    msg = EmailMessage()
    msg["From"] = "robot@clearpath.invalid"
    msg["To"] = recipient["email"]
    msg["Subject"] = subject
    loc = f"{report['lat']}, {report['lon']}" if report.get("lat") is not None else "not provided"
    map_link = (f"https://www.openstreetmap.org/?mlat={report['lat']}&mlon={report['lon']}#map=19/{report['lat']}/{report['lon']}"
                if report.get("lat") is not None else "")
    msg.set_content(
        f"To: {recipient['agency']},\n\n"
        f"ClearPath received a report about an accessibility barrier and forwards it for action.\n\n"
        f"Protocol: {report['protocol']}\n"
        f"Category: {CATEGORIES.get(report['category'], report['category'])}\n"
        f"Priority: {report['priority'].upper()} (score {report['urgency_points']})\n"
        f"Reasons: {report.get('urgency_reasons') or '-'}\n"
        f"Address mentioned: {report.get('address') or '-'}\n"
        f"Coordinates: {loc} {map_link}\n"
        f"Photo assessment: {report.get('damage_level') or 'no photo'}\n"
        f"Response deadline (SLA): {report['deadline'][:10]}\n"
        f"Legal basis: {agencies()['categories'].get(report['category'], {}).get('legal_basis', '-')}\n\n"
        f"Citizen's report (anonymized):\n\"{report['anonymized_text']}\"\n\n"
        f"{extra_body}"
        f"Update the progress at PATCH /api/reports/{report['protocol']}/status.\n"
        f"Automatically generated message. Demo environment: not sent."
    )
    kind = subject.split("]")[0].strip("[").lower()
    path = config.LETTERS_DIR / f"{report['protocol']}_{kind}.eml"
    path.write_bytes(bytes(msg))
    return path


def record_status(con: sqlite3.Connection, protocol: str, status: str, note: str = ""):
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status: {status}. Use one of {VALID_STATUSES}")
    con.execute("UPDATE reports SET status=?, updated_at=? WHERE protocol=?", (status, db.iso(), protocol))
    con.execute("INSERT INTO history (protocol, at, status, note) VALUES (?,?,?,?)",
                (protocol, db.iso(), status, note))


def forward(con: sqlite3.Connection, report: dict) -> Path | None:
    """Forwards automatically, unless the classifier is unsure."""
    if report["human_review"]:
        record_status(con, report["protocol"], "human_triage",
                      f"Confidence {report['confidence']:.0%} below the threshold: a public servant must confirm the category.")
        return None
    recipient = agencies()["categories"][report["category"]]
    extra = ""
    if report.get("group_root"):
        extra = f"This report reinforces occurrence {report['group_root']} (same barrier, another citizen).\n\n"
    path = write_letter(report, recipient, f"[FORWARDING] ClearPath {report['protocol']} - {report['priority']}", extra)
    record_status(con, report["protocol"], "forwarded", f"Automatic letter to {recipient['agency']}")
    return path


def escalate_overdue(con: sqlite3.Connection, reference: datetime | None = None) -> list[str]:
    """Scheduled routine (RPA): escalates everything past its deadline to the Ombudsman."""
    reference = reference or db.now()
    overdue = con.execute(
        "SELECT * FROM reports WHERE status IN ('forwarded','in_progress') AND deadline < ?",
        (db.iso(reference),),
    ).fetchall()
    ombudsman = agencies()["ombudsman"]
    escalated = []
    with db.transaction(con):
        for r in overdue:
            r = dict(r)
            write_letter(r, ombudsman, f"[ESCALATION] Deadline missed {r['protocol']}",
                         f"The agency {r['agency']} did not complete the service by {r['deadline'][:10]}.\n\n")
            record_status(con, r["protocol"], "escalated", "Deadline missed: sent to the Ombudsman")
            db.audit(con, "automatic_escalation", r["protocol"], "SLA missed")
            escalated.append(r["protocol"])
    return escalated
