"""Data governance and protection (LGPD - Brazil's General Data Protection Law, Law 13,709/2018).

Principles applied:
- Minimization: the system does NOT ask for name, CPF (Brazilian taxpayer ID) or contact details.
  Citizens track their report with the protocol number.
- Anonymization on input: if a person writes personal data in the text, it is masked
  before anything is stored.
- Pseudonymization: we keep only a hash (SHA-256 + salt) of the original text to detect
  repeated submissions, never the original.
- Metadata removal: photos are decoded and re-encoded, which drops EXIF data (including the
  phone's GPS position and device model).
- Traceability: every processing step writes an audit record (what, when, legal basis).
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from . import config

# Order matters: CPF before PHONE, because an unformatted CPF also matches the phone pattern.
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")),
    ("CPF", re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")),
    ("PHONE", re.compile(r"(?:\(?\b\d{2}\)?\s?)?\b9?\d{4}[-\s]?\d{4}\b")),
    ("PLATE", re.compile(r"\b[A-Z]{3}-?\d[A-Z0-9]\d{2}\b", re.IGNORECASE)),
    ("NAME", re.compile(r"\b((?i:my name is|i am called|i'm|i am))\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)")),
]


@dataclass
class AnonymizationResult:
    text: str
    found: dict[str, int] = field(default_factory=dict)

    @property
    def had_personal_data(self) -> bool:
        return bool(self.found)


def anonymize(text: str) -> AnonymizationResult:
    """Replaces personal data with markers such as [CPF] and counts what was removed."""
    found: dict[str, int] = {}
    out = text
    for label, pattern in PATTERNS:
        if label == "NAME":
            out, n = pattern.subn(lambda m: f"{m.group(1)} [NAME]", out)
        else:
            out, n = pattern.subn(f"[{label}]", out)
        if n:
            found[label] = n
    return AnonymizationResult(out, found)


def pseudonym(value: str) -> str:
    """Irreversible salted hash, used only to detect duplicates."""
    return hashlib.sha256((config.HASH_SALT + value.strip().lower()).encode("utf-8")).hexdigest()[:16]


def reduce_coordinate_precision(lat: float | None, lon: float | None, places: int = 4):
    """4 decimal places = ~11 m. Enough to find the barrier, and it avoids exposing
    the exact position of the person who reported it (for example, their own home)."""
    if lat is None or lon is None:
        return None, None
    return round(lat, places), round(lon, places)


LEGAL_BASIS = (
    "LGPD art. 7, III and art. 23 - execution of public policies by the public administration; "
    "incidental personal data is anonymized (art. 12)."
)
