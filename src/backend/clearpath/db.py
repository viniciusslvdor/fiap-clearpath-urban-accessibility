"""Persistence with SQLite (Python standard library)."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    protocol TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    source TEXT NOT NULL,                 -- citizen | iot
    anonymized_text TEXT NOT NULL,
    text_hash TEXT NOT NULL,              -- pseudonym of the original text (duplicate detection)
    category TEXT NOT NULL,
    confidence REAL NOT NULL,
    human_review INTEGER NOT NULL DEFAULT 0,
    address TEXT,
    lat REAL,
    lon REAL,
    urgency_points INTEGER NOT NULL,
    urgency_reasons TEXT,
    priority TEXT NOT NULL,
    damage_index REAL,
    damage_level TEXT,
    photo TEXT,
    photo_analysis TEXT,
    group_root TEXT,                      -- protocol of the first report about the same barrier
    agency TEXT NOT NULL,
    deadline TEXT NOT NULL,
    status TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    device TEXT
);
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    protocol TEXT NOT NULL REFERENCES reports(protocol),
    at TEXT NOT NULL,
    status TEXT NOT NULL,
    note TEXT
);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    action TEXT NOT NULL,
    protocol TEXT,
    detail TEXT,
    legal_basis TEXT
);
CREATE TABLE IF NOT EXISTS iot_devices (
    id TEXT PRIMARY KEY,
    location TEXT,
    lat REAL,
    lon REAL,
    last_seen TEXT,
    last_state TEXT,
    distance_cm REAL
);
CREATE TABLE IF NOT EXISTS iot_readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device TEXT NOT NULL,
    at TEXT NOT NULL,
    event TEXT NOT NULL,
    distance_cm REAL,
    duration_s REAL,
    raw TEXT
);
CREATE INDEX IF NOT EXISTS ix_reports_cat ON reports(category, status);
"""


def now() -> datetime:
    return datetime.now(timezone.utc).astimezone()


def iso(dt: datetime | None = None) -> str:
    return (dt or now()).isoformat(timespec="seconds")


def connect(path: Path | None = None) -> sqlite3.Connection:
    path = path or config.DB_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(SCHEMA)
    return con


@contextmanager
def transaction(con: sqlite3.Connection):
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise


def audit(con: sqlite3.Connection, action: str, protocol: str | None = None, detail: str = "", legal_basis: str = ""):
    con.execute(
        "INSERT INTO audit_log (at, action, protocol, detail, legal_basis) VALUES (?,?,?,?,?)",
        (iso(), action, protocol, detail, legal_basis),
    )


def next_protocol(con: sqlite3.Connection) -> str:
    year = now().year
    n = con.execute("SELECT COUNT(*) FROM reports WHERE protocol LIKE ?", (f"CP-{year}-%",)).fetchone()[0]
    return f"CP-{year}-{n + 1:06d}"
