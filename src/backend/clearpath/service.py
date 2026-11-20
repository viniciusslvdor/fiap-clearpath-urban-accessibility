"""Orchestrates the full pipeline of a report. Used by the REST API and by the MQTT bridge."""
from __future__ import annotations

import json
import sqlite3
from datetime import timedelta

import cv2

from . import config, db, governance, nlp, routing, vision

MIN_TEXT_LENGTH = 10
MAX_TEXT_LENGTH = 2000
MAX_PHOTO_SIZE = 8 * 1024 * 1024
SOURCE_LABEL = {"citizen": "through the citizen app", "iot": "from the IoT sensor"}


class ValidationError(ValueError):
    pass


def process_report(
    con: sqlite3.Connection,
    text: str,
    lat: float | None = None,
    lon: float | None = None,
    photo: bytes | None = None,
    source: str = "citizen",
    forced_category: str | None = None,
    device: str | None = None,
) -> dict:
    text = (text or "").strip()
    if not MIN_TEXT_LENGTH <= len(text) <= MAX_TEXT_LENGTH:
        raise ValidationError(f"The report must have between {MIN_TEXT_LENGTH} and {MAX_TEXT_LENGTH} characters.")
    if (lat is None) != (lon is None):
        raise ValidationError("Provide latitude and longitude together.")
    if lat is not None and not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValidationError("Invalid coordinates.")
    if photo and len(photo) > MAX_PHOTO_SIZE:
        raise ValidationError("Photo larger than 8 MB.")

    config.ensure_dirs()

    # 1. Governance: anonymize BEFORE anything is stored
    anon = governance.anonymize(text)
    text_hash = governance.pseudonym(text)
    lat, lon = governance.reduce_coordinate_precision(lat, lon)

    since = db.iso(db.now() - timedelta(hours=24))
    repeated = con.execute(
        "SELECT protocol FROM reports WHERE text_hash=? AND created_at>=?", (text_hash, since)
    ).fetchone()
    if repeated:
        return {**get_report(con, repeated["protocol"]), "duplicate": True}

    if forced_category:
        cat, label, conf, review, alternatives = forced_category, nlp.CATEGORIES[forced_category], 1.0, False, []
    else:
        c = nlp.classify(anon.text)
        cat, label, conf, review, alternatives = c.category, c.label, c.confidence, c.human_review, c.alternatives
    address = nlp.extract_address(anon.text)
    points, reasons = nlp.score_urgency(anon.text, cat)

    with db.transaction(con):
        protocol = db.next_protocol(con)

        analysis = None
        photo_file = analysis_file = None
        if photo:
            img = vision.decode(photo)
            clean = vision.reencode_without_metadata(img)
            photo_file = f"{protocol}.jpg"
            (config.MEDIA_DIR / photo_file).write_bytes(clean)
            analysis, overlay = vision.analyze(img)
            analysis_file = f"{protocol}_analysis.jpg"
            cv2.imwrite(str(config.MEDIA_DIR / analysis_file), overlay)
            if bonus := routing.vision_bonus(analysis.level):
                points += bonus
                reasons.append(f"photo shows {analysis.level} damage")

        root, group_size = routing.find_group(con, cat, lat, lon)
        if group_size:
            points += min(30, 10 * group_size)
            reasons.append(f"{group_size} other report(s) about the same barrier")
        points = min(points, 100)

        priority = routing.priority_from_points(points)
        deadline = routing.compute_deadline(priority)
        agency = routing.agencies()["categories"][cat]["agency"]

        record = {
            "protocol": protocol,
            "created_at": db.iso(),
            "source": source,
            "anonymized_text": anon.text,
            "text_hash": text_hash,
            "category": cat,
            "confidence": conf,
            "human_review": int(review),
            "address": address,
            "lat": lat,
            "lon": lon,
            "urgency_points": points,
            "urgency_reasons": "; ".join(reasons),
            "priority": priority,
            "damage_index": analysis.damage_index if analysis else None,
            "damage_level": analysis.level if analysis else None,
            "photo": photo_file,
            "photo_analysis": analysis_file,
            "group_root": root,
            "agency": agency,
            "deadline": db.iso(deadline),
            "status": "received",
            "updated_at": db.iso(),
            "device": device,
        }
        con.execute(
            f"INSERT INTO reports ({','.join(record)}) VALUES ({','.join('?' * len(record))})",
            tuple(record.values()),
        )
        con.execute("INSERT INTO history (protocol, at, status, note) VALUES (?,?,?,?)",
                    (protocol, db.iso(), "received", "Report received " + SOURCE_LABEL.get(source, source)))
        if root:
            reinforce_occurrence(con, root, protocol)
        db.audit(con, "report_collected", protocol,
                 json.dumps({"personal_data_removed": anon.found, "photo_without_exif": bool(photo)}),
                 governance.LEGAL_BASIS)

        routing.forward(con, record)

    result = get_report(con, protocol)
    result["alternatives"] = alternatives
    result["personal_data_removed"] = anon.found
    result["image_analysis"] = analysis.to_dict() if analysis else None
    result["category_label"] = label
    return result


def reinforce_occurrence(con: sqlite3.Connection, root: str, new: str):
    r = con.execute("SELECT urgency_points, priority, status FROM reports WHERE protocol=?", (root,)).fetchone()
    if not r:
        return
    points = min(100, r["urgency_points"] + 10)
    priority = routing.priority_from_points(points)
    con.execute("UPDATE reports SET urgency_points=?, priority=?, updated_at=? WHERE protocol=?",
                (points, priority, db.iso(), root))
    note = f"New report about the same barrier ({new})"
    if priority != r["priority"]:
        note += f": priority raised from {r['priority']} to {priority}"
    con.execute("INSERT INTO history (protocol, at, status, note) VALUES (?,?,?,?)",
                (root, db.iso(), r["status"], note))


def get_report(con: sqlite3.Connection, protocol: str) -> dict | None:
    r = con.execute("SELECT * FROM reports WHERE protocol=?", (protocol,)).fetchone()
    if not r:
        return None
    d = dict(r)
    d.pop("text_hash", None)
    d["human_review"] = bool(d["human_review"])
    d["category_label"] = nlp.CATEGORIES.get(d["category"], d["category"])
    d["history"] = [dict(h) for h in con.execute(
        "SELECT at, status, note FROM history WHERE protocol=? ORDER BY id", (protocol,))]
    return d


def erase_data(con: sqlite3.Connection, protocol: str) -> bool:
    """Right to erasure (LGPD art. 18, VI): deletes photos and free text,
    keeping only the statistical fields (category, approximate location, dates)."""
    r = con.execute("SELECT photo, photo_analysis FROM reports WHERE protocol=?", (protocol,)).fetchone()
    if not r:
        return False
    with db.transaction(con):
        for f in (r["photo"], r["photo_analysis"]):
            if f:
                (config.MEDIA_DIR / f).unlink(missing_ok=True)
        con.execute("UPDATE reports SET anonymized_text='[removed at the data subject''s request]', photo=NULL, "
                    "photo_analysis=NULL, updated_at=? WHERE protocol=?", (db.iso(), protocol))
        db.audit(con, "erasure_on_request", protocol, "photos and text removed", "LGPD art. 18, VI")
    return True


def apply_retention(con: sqlite3.Connection, reference=None) -> list[str]:
    """Retention policy: deletes photos of reports resolved more than PHOTO_RETENTION_DAYS ago.
    Run by the daily robot (scripts/sla_robot.py)."""
    reference = reference or db.now()
    limit = db.iso(reference - timedelta(days=config.PHOTO_RETENTION_DAYS))
    targets = con.execute(
        "SELECT r.protocol, r.photo, r.photo_analysis FROM reports r JOIN history h ON h.protocol = r.protocol "
        "WHERE r.status='resolved' AND h.status='resolved' AND h.at < ? AND r.photo IS NOT NULL",
        (limit,),
    ).fetchall()
    with db.transaction(con):
        for r in targets:
            for f in (r["photo"], r["photo_analysis"]):
                (config.MEDIA_DIR / f).unlink(missing_ok=True)
            con.execute("UPDATE reports SET photo=NULL, photo_analysis=NULL WHERE protocol=?", (r["protocol"],))
            db.audit(con, "photo_retention", r["protocol"],
                     f"photos deleted {config.PHOTO_RETENTION_DAYS} days after resolution", "LGPD arts. 15 and 16")
    return [r["protocol"] for r in targets]
