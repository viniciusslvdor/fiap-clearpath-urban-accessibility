"""Natural language processing of citizen reports.

Steps:
1. Preprocessing: lowercase, accent removal, anonymization markers, digits and
   punctuation removed; tokenization and stopword removal.
2. Representation: word TF-IDF (1- and 2-grams) combined with character n-gram
   TF-IDF (3 to 5). Character n-grams make the model tolerant to typos
   ("sidewlak", "side walk") and to inflections ("ramp"/"ramps").
3. Classification: linear model trained in scripts/train_model.py.
4. Information extraction: address and urgency signals through lexical rules.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

import joblib

from . import config

CATEGORIES = {
    "damaged_sidewalk": "Damaged sidewalk",
    "sidewalk_obstruction": "Sidewalk obstruction",
    "ramp_access": "Ramp / building access",
    "tactile_paving": "Tactile paving",
    "crossing_signal": "Crossing and pedestrian signal",
    "accessible_transit": "Accessible public transit",
}

CONFIDENCE_THRESHOLD = 0.50  # below this the report goes to human triage (see report, NLP section)

STOPWORDS = set(
    """a about after all also am an and any are as at be been but by can could did do does for from
    had has have he her here him his how i if in into is it its just me more my no not of on or our
    out over she so some than that the their them then there these they this to too up us very was
    we were what when where which who will with would you your yours i'm im it's dont don't cant can't
    hi hello please thanks thank good morning someone somebody needs need look want would like report
    complain""".split()
)

_MARKER_RE = re.compile(r"\[(cpf|phone|email|plate|name)\]", re.IGNORECASE)
_NON_LETTER_RE = re.compile(r"[^a-z\s]")
_SPACES_RE = re.compile(r"\s+")


def remove_accents(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()


def normalize(text: str) -> str:
    """Clean text used by the vectorizers (this function is also referenced by the saved pipeline)."""
    t = _MARKER_RE.sub(" ", text)
    t = remove_accents(t.lower())
    t = t.replace("'", "")
    t = _NON_LETTER_RE.sub(" ", t)
    return _SPACES_RE.sub(" ", t).strip()


def tokenize(text: str) -> list[str]:
    return [tok for tok in normalize(text).split() if tok not in STOPWORDS and len(tok) > 1]


# ----------------------------------------------------------------- urgency ---
# Weights chosen by hand: people most exposed to risk and reports of physical
# harm raise the priority. The list is explainable and auditable, unlike an opaque
# model, which is desirable in a public service.
URGENCY_SIGNALS: dict[str, tuple[int, str]] = {
    r"\b(fell|fall|falls|falling|tripped|trip|injured|injury|hurt|accident|run over|hit by)\b": (30, "fall or accident reported"),
    r"\b(wheelchair|blind|visually impaired|white cane|cane|low vision|crutches|walker)\b": (20, "person with disability affected"),
    r"\b(elderly|old lady|old man|senior|seniors|child|children|kids|baby|stroller|pram|pregnant)\b": (12, "vulnerable person affected"),
    r"\b(hospital|clinic|health center|health unit|school|daycare|station|terminal)\b": (12, "near an essential service"),
    r"\b(dangerous|danger|risk|risky|urgent|help|huge|crater)\b": (10, "risk declared"),
    r"\b(into the street|onto the street|in the street|among the cars|cant get through|can not get through|cannot get through|stuck|trapped)\b": (15, "pedestrian forced into the street"),
    r"\b(months|weeks|for days|a month|again|always|every night|every day|before|still)\b": (8, "recurring problem"),
    r"\bramps?\b.{0,40}\b(obstruct|block|parked|park)\w*|\b(obstruct|block|parked|park)\w*.{0,40}\bramps?\b":
        (20, "ramp blocked: accessible route interrupted"),
}
_COMPILED_SIGNALS = [(re.compile(p), w, reason) for p, (w, reason) in URGENCY_SIGNALS.items()]

# Base weight per category: failures that remove the autonomy of blind people or
# wheelchair users (no alternative route) start higher.
CATEGORY_WEIGHT = {
    "damaged_sidewalk": 20,
    "sidewalk_obstruction": 15,
    "ramp_access": 25,
    "tactile_paving": 25,
    "crossing_signal": 30,
    "accessible_transit": 25,
}


def score_urgency(text: str, category: str) -> tuple[int, list[str]]:
    t = normalize(text)
    points = CATEGORY_WEIGHT.get(category, 15)
    reasons = []
    for pattern, weight, reason in _COMPILED_SIGNALS:
        if pattern.search(t):
            points += weight
            reasons.append(reason)
    return min(points, 100), reasons


# ----------------------------------------------------------------- address ---
_NAME = r"[A-Z][\w'À-ÿ.]*(?:\s+(?:d[aeo]s?|[A-Z][\w'À-ÿ.]*)){0,4}"
# São Paulo style: "Rua Augusta, 1500", "Av. Paulista" (street names are proper nouns)
_ADDRESS_PREFIX_RE = re.compile(
    rf"\b((?:Rua|R\.|Avenida|Av\.?|Alameda|Al\.|Travessa|Estrada|Praça|Praca|Largo)\s+{_NAME})"
    r"(?:,?\s*(?:no\.?|n[ºo°]\.?|number|#)?\s*(\d{1,5}))?"
)
# English style: "1500 Augusta Street", "Paulista Avenue"
_ADDRESS_SUFFIX_RE = re.compile(
    r"\b(?:(\d{1,5})\s+)?((?:[A-Z][\w'À-ÿ]*\s+){1,4}(?:Street|St\.|Avenue|Ave\.|Road|Rd\.|Boulevard|Square|Lane))"
    r"(?:,?\s*(?:no\.?|number|#)\s*(\d{1,5}))?"
)
_STOP_WORDS_ADDRESS = {"near", "in", "on", "at", "by", "next", "close", "with", "and", "the", "is", "has"}


def extract_address(text: str) -> str | None:
    for m in _ADDRESS_PREFIX_RE.finditer(text):
        words = []
        for w in m.group(1).split():
            if words and w.lower().strip(",.") in _STOP_WORDS_ADDRESS:
                break
            words.append(w.strip(","))
        if len(words) < 2:
            continue
        address = " ".join(words)
        return f"{address}, {m.group(2)}" if m.group(2) else address
    m = _ADDRESS_SUFFIX_RE.search(text)
    if m:
        number = m.group(1) or m.group(3)
        street = " ".join(m.group(2).split())
        return f"{street}, {number}" if number else street
    return None


# ---------------------------------------------------------- classification ---
@dataclass
class Classification:
    category: str
    label: str
    confidence: float
    human_review: bool
    alternatives: list[tuple[str, float]]


@lru_cache(maxsize=1)
def load_model():
    if not config.MODEL_FILE.exists():
        raise FileNotFoundError(f"Model not found at {config.MODEL_FILE}. Run: uv run python scripts/train_model.py")
    return joblib.load(config.MODEL_FILE)


def classify(text: str) -> Classification:
    model = load_model()
    probs = model.predict_proba([text])[0]
    ranking = sorted(zip(model.classes_, probs), key=lambda x: -x[1])
    cat, conf = ranking[0]
    return Classification(
        category=str(cat),
        label=CATEGORIES[str(cat)],
        confidence=round(float(conf), 3),
        human_review=bool(conf < CONFIDENCE_THRESHOLD),
        alternatives=[(str(c), round(float(p), 3)) for c, p in ranking[1:3]],
    )
