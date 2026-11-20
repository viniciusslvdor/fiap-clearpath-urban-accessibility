"""Central paths and parameters for ClearPath."""
from __future__ import annotations

import os
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = BACKEND_ROOT.parent
REPO_ROOT = SRC_ROOT.parent
DATA_DIR = SRC_ROOT / "data"

CHARTS_DIR = REPO_ROOT / "assets" / "charts"
EVIDENCE_DIR = REPO_ROOT / "docs" / "other" / "evidence"

RUNTIME_DIR = Path(os.getenv("CLEARPATH_RUNTIME", DATA_DIR / "runtime"))
MEDIA_DIR = RUNTIME_DIR / "media"
LETTERS_DIR = RUNTIME_DIR / "letters"
REPORTS_DIR = RUNTIME_DIR / "reports"
DB_FILE = RUNTIME_DIR / "clearpath.sqlite3"

MODEL_FILE = BACKEND_ROOT / "models" / "report_classifier.joblib"
AGENCIES_FILE = DATA_DIR / "responsible_agencies.json"

# Salt for the pseudonymization hash. In production this would come from a secrets vault.
HASH_SALT = os.getenv("CLEARPATH_SALT", "demo-salt-change-in-production")

PHOTO_RETENTION_DAYS = 90

GROUPING_RADIUS_M = 60

MQTT_BROKER = os.getenv("CLEARPATH_MQTT_BROKER", "broker.hivemq.com")
MQTT_PORT = int(os.getenv("CLEARPATH_MQTT_PORT", "1883"))
MQTT_TOPIC = os.getenv("CLEARPATH_MQTT_TOPIC", "clearpath/fiap-gs/sensors/#")


def ensure_dirs() -> None:
    for d in (RUNTIME_DIR, MEDIA_DIR, LETTERS_DIR, REPORTS_DIR):
        d.mkdir(parents=True, exist_ok=True)
