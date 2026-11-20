"""Fills the database with a DEMO (simulated) dataset for the dashboard and the video.

The reports go through the real pipeline (anonymization, NLP, vision, routing,
automation). What is simulated is the TIMELINE: dates are moved back up to 30 days
and the agencies' progress (in progress/resolved) is randomly drawn. Therefore every
dashboard indicator built from this data is ILLUSTRATIVE and does not measure real impact.

Usage:
    uv run python scripts/seed_demo.py            # wipes the runtime folder and rebuilds it
"""
from __future__ import annotations

import random
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from clearpath import config, db, iot, routing, service  # noqa: E402
from generate_dataset import TEMPLATES, generate_report  # noqa: E402

# Reference points in São Paulo (lat, lon) around which reports are drawn.
REGIONS = [
    (-23.5614, -46.6559, "Av. Paulista"),
    (-23.5489, -46.6388, "Downtown / Sé"),
    (-23.5431, -46.6291, "Brás"),
    (-23.6234, -46.6993, "Santo Amaro"),
    (-23.5868, -46.5930, "Sapopemba"),
    (-23.4950, -46.6990, "Freguesia do Ó"),
    (-23.5340, -46.7380, "Lapa"),
]
# "Hot spots": the same barrier reported by several people (tests grouping).
HOT_SPOTS = [
    (-23.55785, -46.66230, "damaged_sidewalk"),
    (-23.54512, -46.63391, "ramp_access"),
    (-23.61950, -46.70210, "crossing_signal"),
]


def shift_timeline(con, protocol: str, days: float):
    delta = timedelta(days=days)
    r = con.execute("SELECT created_at, deadline FROM reports WHERE protocol=?", (protocol,)).fetchone()
    shifted = lambda s: db.iso(datetime.fromisoformat(s) - delta)  # noqa: E731
    con.execute("UPDATE reports SET created_at=?, deadline=?, updated_at=? WHERE protocol=?",
                (shifted(r["created_at"]), shifted(r["deadline"]), shifted(r["created_at"]), protocol))
    for h in con.execute("SELECT id, at FROM history WHERE protocol=?", (protocol,)).fetchall():
        con.execute("UPDATE history SET at=? WHERE id=?", (shifted(h["at"]), h["id"]))


def advance_status(con, protocol: str, days_ago: float, rng: random.Random):
    """Simulates the agency's response: some reports are resolved on time, some are late."""
    r = con.execute("SELECT status FROM reports WHERE protocol=?", (protocol,)).fetchone()
    if r["status"] != "forwarded" or days_ago < 1:
        return
    start = db.now() - timedelta(days=days_ago)
    t_work = start + timedelta(days=rng.uniform(0.5, min(3, days_ago)))
    if rng.random() < 0.75:
        con.execute("INSERT INTO history (protocol, at, status, note) VALUES (?,?,?,?)",
                    (protocol, db.iso(t_work), "in_progress", "Crew assigned (simulated)"))
        con.execute("UPDATE reports SET status='in_progress', updated_at=? WHERE protocol=?", (db.iso(t_work), protocol))
        t_done = t_work + timedelta(days=rng.uniform(0.5, 18))
        if t_done < db.now() and rng.random() < 0.7:
            con.execute("INSERT INTO history (protocol, at, status, note) VALUES (?,?,?,?)",
                        (protocol, db.iso(t_done), "resolved", "Service completed (simulated)"))
            con.execute("UPDATE reports SET status='resolved', updated_at=? WHERE protocol=?", (db.iso(t_done), protocol))


def main(n_reports: int = 140, seed: int = 7):
    rng = random.Random(seed)
    if config.RUNTIME_DIR.exists():
        shutil.rmtree(config.RUNTIME_DIR)
    config.ensure_dirs()
    con = db.connect()

    blind = pd.read_csv(config.DATA_DIR / "reports_blind_test.csv")
    texts = list(zip(blind.text, blind.category))
    while len(texts) < n_reports:
        cat = rng.choice(list(TEMPLATES))
        texts.append((generate_report(cat, rng), cat))
    rng.shuffle(texts)

    img_dir = config.DATA_DIR / "demo_images" / "test"
    photos = {n: sorted(img_dir.glob(f"{n}_*.jpg")) for n in ("moderate", "severe", "no_visible_damage")}

    for i, (text, cat) in enumerate(texts):
        if i < 12:  # the first reports go to the hot spots
            lat, lon, hot_cat = HOT_SPOTS[i % 3]
            text = next(t for t, c in texts[12:] if c == hot_cat)
            text = f"{text} (report {i})"
            lat += rng.uniform(-0.0002, 0.0002)
            lon += rng.uniform(-0.0002, 0.0002)
        else:
            blat, blon, _ = rng.choice(REGIONS)
            lat, lon = blat + rng.gauss(0, 0.008), blon + rng.gauss(0, 0.008)
        photo = None
        if cat == "damaged_sidewalk" and rng.random() < 0.6:
            photo = rng.choice(photos[rng.choice(["moderate", "severe", "severe", "no_visible_damage"])]).read_bytes()
        try:
            rep = service.process_report(con, text, lat, lon, photo)
        except service.ValidationError:
            continue
        if rep.get("duplicate"):
            continue
        days = rng.uniform(0, 29.5) if i >= 12 else rng.uniform(0.2, 6)
        with db.transaction(con):
            shift_timeline(con, rep["protocol"], days)
            advance_status(con, rep["protocol"], days, rng)

    # Ramp sensor (the same messages the ESP32 publishes)
    ramp = {"device": "ramp-paulista-01", "location": "Ramp at Av. Paulista x R. Augusta", "lat": -23.5558, "lon": -46.6623}
    for msg in [
        {**ramp, "event": "heartbeat", "distance_cm": 310},
        {**ramp, "event": "obstruction", "distance_cm": 48, "duration_s": 35},
        {**ramp, "event": "confirmation", "distance_cm": 47},
        {"device": "ramp-se-02", "location": "Ramp at Praça da Sé (cathedral side)", "lat": -23.5503, "lon": -46.6340,
         "event": "heartbeat", "distance_cm": 280},
    ]:
        iot.process_message(con, msg)

    escalated = routing.escalate_overdue(con)
    total = con.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
    print(f"Demo dataset created: {total} reports | {len(escalated)} escalated for missed deadlines")
    print(f"Database: {config.DB_FILE}")


if __name__ == "__main__":
    main()
