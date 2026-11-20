"""ClearPath REST API (FastAPI)."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__, config, db, governance, iot, nlp, routing, service

config.ensure_dirs()
con = db.connect()

app = FastAPI(
    title="ClearPath API",
    version=__version__,
    description="Crowdsourced mapping and automatic routing of urban accessibility barriers.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/media", StaticFiles(directory=config.MEDIA_DIR), name="media")


class ClassifyRequest(BaseModel):
    text: str = Field(min_length=3, max_length=2000)


class StatusUpdate(BaseModel):
    status: str
    note: str = ""


class IoTReading(BaseModel):
    device: str
    event: str
    location: str | None = None
    lat: float | None = None
    lon: float | None = None
    distance_cm: float | None = None
    duration_s: float | None = None


@app.get("/api/health")
def health():
    return {"status": "ok", "version": __version__, "nlp_model": config.MODEL_FILE.exists()}


@app.get("/api/categories")
def categories():
    table = routing.agencies()["categories"]
    return [{"id": k, "label": v, "agency": table[k]["agency"], "legal_basis": table[k]["legal_basis"]}
            for k, v in nlp.CATEGORIES.items()]


@app.post("/api/classify")
def classify(req: ClassifyRequest):
    anon = governance.anonymize(req.text)
    c = nlp.classify(anon.text)
    points, reasons = nlp.score_urgency(anon.text, c.category)
    return {
        "anonymized_text": anon.text,
        "personal_data_removed": anon.found,
        "category": c.category,
        "label": c.label,
        "confidence": c.confidence,
        "human_review": c.human_review,
        "alternatives": c.alternatives,
        "address": nlp.extract_address(anon.text),
        "urgency_points": points,
        "reasons": reasons,
        "estimated_priority": routing.priority_from_points(points),
    }


@app.post("/api/reports", status_code=201)
async def create_report(
    text: str = Form(...),
    consent: bool = Form(...),
    lat: float | None = Form(None),
    lon: float | None = Form(None),
    photo: UploadFile | None = File(None),
):
    if not consent:
        raise HTTPException(400, "You must accept the privacy notice to submit the report.")
    content = await photo.read() if photo and photo.filename else None
    try:
        return service.process_report(con, text, lat, lon, content)
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.get("/api/reports")
def list_reports(category: str | None = None, status: str | None = None, priority: str | None = None, limit: int = 500):
    sql = ("SELECT protocol, created_at, source, anonymized_text, category, confidence, address, lat, lon, "
           "priority, urgency_points, damage_level, photo_analysis, group_root, agency, deadline, status FROM reports WHERE 1=1")
    args: list = []
    for column, value in (("category", category), ("status", status), ("priority", priority)):
        if value:
            sql += f" AND {column}=?"
            args.append(value)
    sql += " ORDER BY created_at DESC LIMIT ?"
    args.append(min(limit, 2000))
    rows = [dict(r) for r in con.execute(sql, args)]
    for r in rows:
        r["category_label"] = nlp.CATEGORIES.get(r["category"], r["category"])
    return rows


@app.get("/api/reports/{protocol}")
def get_report(protocol: str):
    r = service.get_report(con, protocol)
    if not r:
        raise HTTPException(404, "Protocol not found.")
    return r


@app.patch("/api/reports/{protocol}/status")
def update_status(protocol: str, body: StatusUpdate):
    if not service.get_report(con, protocol):
        raise HTTPException(404, "Protocol not found.")
    try:
        with db.transaction(con):
            routing.record_status(con, protocol, body.status, body.note)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return service.get_report(con, protocol)


@app.delete("/api/reports/{protocol}/data")
def erase_data(protocol: str):
    """Data subject's right to erasure (LGPD art. 18, VI)."""
    if not service.erase_data(con, protocol):
        raise HTTPException(404, "Protocol not found.")
    return {"protocol": protocol, "data_erased": True}


@app.post("/api/automation/escalate")
def escalate(reference: datetime | None = None):
    return {"escalated": routing.escalate_overdue(con, reference)}


@app.post("/api/iot/readings")
def iot_reading(reading: IoTReading):
    try:
        return iot.process_message(con, reading.model_dump())
    except service.ValidationError as e:
        raise HTTPException(422, str(e))


@app.get("/api/iot/devices")
def devices():
    rows = [dict(r) for r in con.execute("SELECT * FROM iot_devices ORDER BY id")]
    for d in rows:
        d["readings"] = [dict(r) for r in con.execute(
            "SELECT at, event, distance_cm, duration_s FROM iot_readings WHERE device=? ORDER BY id DESC LIMIT 20",
            (d["id"],))]
    return rows


@app.get("/api/indicators")
def indicators():
    reports = [dict(r) for r in con.execute("SELECT * FROM reports")]
    hist = [dict(r) for r in con.execute("SELECT protocol, at, status FROM history ORDER BY id")]
    resolved_at = {h["protocol"]: h["at"] for h in hist if h["status"] == "resolved"}
    forwarded_at = {}
    for h in hist:
        if h["status"] == "forwarded":
            forwarded_at.setdefault(h["protocol"], h["at"])

    total = len(reports)
    resolved = [r for r in reports if r["status"] == "resolved"]
    on_time = [r for r in resolved if resolved_at.get(r["protocol"], r["updated_at"]) <= r["deadline"]]
    days_to_resolve = [
        (datetime.fromisoformat(resolved_at[r["protocol"]]) - datetime.fromisoformat(r["created_at"])).total_seconds() / 86400
        for r in resolved if r["protocol"] in resolved_at
    ]
    seconds_to_forward = [
        (datetime.fromisoformat(forwarded_at[r["protocol"]]) - datetime.fromisoformat(r["created_at"])).total_seconds()
        for r in reports if r["protocol"] in forwarded_at
    ]
    today = db.now().date()
    series = Counter(r["created_at"][:10] for r in reports)
    pii = sum(1 for a in con.execute("SELECT detail FROM audit_log WHERE action='report_collected'")
              if '"personal_data_removed": {}' not in (a["detail"] or ""))
    groups = Counter(r["group_root"] or r["protocol"] for r in reports if r["status"] != "resolved")
    top = []
    for root, n in groups.most_common(5):
        base = next((r for r in reports if r["protocol"] == root), None)
        if base and n > 1:
            top.append({"protocol": root, "reports": n, "category": nlp.CATEGORIES[base["category"]],
                        "address": base["address"], "priority": base["priority"]})

    return {
        "total_reports": total,
        "open": sum(1 for r in reports if r["status"] in routing.OPEN_STATUSES),
        "resolved": len(resolved),
        "on_time_resolution_rate": round(len(on_time) / len(resolved), 3) if resolved else None,
        "avg_days_to_resolve": round(sum(days_to_resolve) / len(days_to_resolve), 1) if days_to_resolve else None,
        "avg_seconds_to_forward": round(sum(seconds_to_forward) / len(seconds_to_forward), 2) if seconds_to_forward else None,
        "auto_forwarded": len(forwarded_at),
        "human_triage": sum(1 for r in reports if r["status"] == "human_triage"),
        "escalated": sum(1 for r in reports if r["status"] == "escalated"),
        "overdue_open": sum(1 for r in reports if r["status"] in ("forwarded", "in_progress") and r["deadline"] < db.iso()),
        "iot_reports": sum(1 for r in reports if r["source"] == "iot"),
        "reports_with_personal_data_removed": pii,
        "by_category": {nlp.CATEGORIES[k]: v for k, v in Counter(r["category"] for r in reports).most_common()},
        "by_priority": {p: sum(1 for r in reports if r["priority"] == p) for p in ("critical", "high", "medium", "low")},
        "by_status": dict(Counter(r["status"] for r in reports)),
        "last_30_days": [{"day": (d := (today - timedelta(days=i)).isoformat()), "reports": series.get(d, 0)} for i in range(29, -1, -1)],
        "most_reported_barriers": top,
    }
