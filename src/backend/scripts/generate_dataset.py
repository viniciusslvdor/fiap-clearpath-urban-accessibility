"""Generates the DEMO (synthetic) dataset of accessibility barrier reports.

IMPORTANT: the texts are synthetic. They are built from sentence templates written for
this project, inspired by the vocabulary of public maintenance complaints and by the items
of the ABNT NBR 9050 accessibility standard. No report comes from a real citizen.
Personal data (CPF, phone, e-mail) is made up and appears on purpose, to test the
anonymization step.

Usage:
    uv run python scripts/generate_dataset.py            # writes src/data/reports_train.csv
"""
from __future__ import annotations

import csv
import random
from pathlib import Path

SEED = 42
PER_CATEGORY = 220

SRC_ROOT = Path(__file__).resolve().parents[2]
OUTPUT = SRC_ROOT / "data" / "reports_train.csv"

STREETS = [
    "Rua Augusta", "Av. Paulista", "Rua da Consolação", "Rua Vergueiro", "Av. Sapopemba",
    "Rua Teodoro Sampaio", "Av. Brigadeiro Faria Lima", "Rua Domingos de Morais",
    "Estrada do M'Boi Mirim", "Av. Celso Garcia", "Rua Voluntários da Pátria",
    "Av. Jabaquara", "Rua Cardeal Arcoverde", "Av. Inajar de Souza", "Rua Tuiuti",
]
REFERENCES = [
    "near the bakery", "in front of the health clinic", "on the corner by the pharmacy",
    "next to the public school", "at the station exit", "in front of the supermarket",
    "near the bus stop", "in front of the church", "next to the hospital", "",
]
PEOPLE = [
    "I use a wheelchair", "my mother is elderly and uses a walker", "I am visually impaired",
    "I push a stroller every day", "I walk with crutches", "my son is autistic and gets scared easily",
    "I have reduced mobility", "I go with my father who uses a wheelchair",
    "I am blind and walk with a white cane", "", "", "",
]
IMPACTS = [
    "I have seen people fall there", "I had to walk into the street among the cars", "I almost fell yesterday",
    "I can't get through", "it is very dangerous", "this has been going on for months", "nobody fixes it",
    "an old lady got hurt last week", "I get stuck and can't cross", "",
]
PII = [
    "my cpf is {cpf}", "my phone is {tel}", "call me at {tel}", "email {email}",
    "contact: {email}", "", "", "", "", "", "", "",
]

TEMPLATES = {
    "damaged_sidewalk": [
        "the sidewalk is completely broken on {street}",
        "huge hole in the sidewalk {ref}",
        "loose and sunken paving on the sidewalk of {street}",
        "tree roots lifted the sidewalk {ref}",
        "big uneven step on the pavement of {street}",
        "sidewalk full of potholes and cracks {ref}",
        "broken tile on the sidewalk, you can twist your ankle",
        "the pavement collapsed and opened a crater {ref}",
        "a step in the middle of the sidewalk with no signage on {street}",
        "loose cobblestones on the sidewalk {ref}",
        "public sidewalk destroyed after the water company's works",
        "sunken manhole cover on the sidewalk of {street}",
    ],
    "sidewalk_obstruction": [
        "car parked on top of the sidewalk {ref}",
        "construction debris blocking the sidewalk on {street}",
        "the bar's tables and chairs take up the whole sidewalk {ref}",
        "garbage bags left in the middle of the sidewalk on {street}",
        "motorcycle parked on the sidewalk blocking the way {ref}",
        "a shop put its goods on the sidewalk and you can't get past",
        "fallen tree branches closing the sidewalk {ref}",
        "a dumpster sitting on the sidewalk on {street}",
        "a car parked in front of the ramp every night {ref}",
        "a newsstand and advertising boards block the way on {street}",
        "a pole and a sign in the middle of the narrow sidewalk {ref}",
        "building materials spread out blocking the passage",
    ],
    "ramp_access": [
        "there is no curb ramp at the corner of {street}",
        "the ramp is too steep {ref}, the wheelchair rolls back",
        "broken accessibility ramp on {street}",
        "the ramp ends in a step, it is useless {ref}",
        "missing curb cut at the crossing of {street}",
        "curb ramp only on one side of the street {ref}",
        "ramp too narrow for a wheelchair on {street}",
        "the health clinic entrance only has stairs, no ramp",
        "ramp with a hole in the middle {ref}",
        "there is no ramp to get onto the sidewalk of {street}",
        "the ramp slope does not meet the standard {ref}",
        "public building with no ramp and no handrail on {street}",
    ],
    "tactile_paving": [
        "tactile paving ripped out on {street}",
        "the tactile guide path leads straight into a pole {ref}",
        "no tactile paving at the crosswalk on {street}",
        "tactile paving faded and broken {ref}",
        "tactile strip interrupted in the middle of the path on {street}",
        "warning tactile tiles covered by an asphalt patch {ref}",
        "the tactile guide line ends at a tree",
        "there is no tactile paving at the station {ref}",
        "tactile paving installed wrong, it leads into the wall on {street}",
        "loose and slippery tactile strip {ref}",
        "the directional tactile path disappears in front of the terminal",
        "the platform tactile paving is worn out and you can't feel it",
    ],
    "crossing_signal": [
        "traffic light without an audible signal on {street}",
        "pedestrian light time is too short {ref}",
        "faded crosswalk on {street}",
        "the pedestrian push button is broken {ref}",
        "no crosswalk and no traffic light on {street}",
        "the light turns red before you have time to cross {ref}",
        "pedestrian traffic light off for days on {street}",
        "crossing with no refuge island, the avenue is too wide",
        "the audible crossing signal is not working {ref}",
        "raised crosswalk with no signage on {street}",
        "drivers ignore the crosswalk because it is all faded {ref}",
        "dangerous intersection with no pedestrian signal on {street}",
    ],
    "accessible_transit": [
        "the station elevator is broken again {ref}",
        "bus wheelchair lift broken on the {street} line",
        "the driver did not stop for a wheelchair user at the stop {ref}",
        "bus stop without an accessible sidewalk on {street}",
        "metro escalator and elevator out of service {ref}",
        "bus with no space for a wheelchair",
        "huge gap between the train and the platform {ref}",
        "no audio announcement of the stops inside the bus",
        "the bus shelter blocks the way on {street}",
        "terminal elevator closed for weeks {ref}",
        "the bus ramp won't open, the driver said it is broken",
        "station with no braille signage {ref}",
    ],
}

OPENINGS = ["", "", "Good morning, ", "Hello, ", "I want to complain: ", "Urgent! ", "Please, ", "Help, "]
CLOSINGS = ["", "", " Please fix it.", " I ask for action.", " I have complained before.", " Thank you.", "!!", " Someone needs to look at this."]


def _cpf(r: random.Random) -> str:
    n = [r.randint(0, 9) for _ in range(11)]
    return f"{''.join(map(str, n[:3]))}.{''.join(map(str, n[3:6]))}.{''.join(map(str, n[6:9]))}-{''.join(map(str, n[9:]))}"


def _phone(r: random.Random) -> str:
    return f"(11) 9{r.randint(1000, 9999)}-{r.randint(1000, 9999)}"


def _email(r: random.Random) -> str:
    name = r.choice(["john", "mary.s", "ana_paula", "carlos88", "bia.lima"])
    return f"{name}{r.randint(1, 99)}@example.com"


def _noise(text: str, r: random.Random) -> str:
    """Simulates informal writing: no apostrophes, mixed case and typos."""
    if r.random() < 0.30:
        text = text.replace("'", "")
    if r.random() < 0.15:
        text = text.upper()
    elif r.random() < 0.20:
        text = text.lower()
    if r.random() < 0.20 and len(text) > 20:
        i = r.randint(5, len(text) - 5)
        text = text[:i] + text[i + 1] + text[i] + text[i + 2:]
    return text


def generate_report(category: str, r: random.Random) -> str:
    base = r.choice(TEMPLATES[category]).format(street=r.choice(STREETS), ref=r.choice(REFERENCES))
    parts = [r.choice(OPENINGS) + base]
    for options in (PEOPLE, IMPACTS):
        extra = r.choice(options)
        if extra:
            parts.append(extra)
    pii = r.choice(PII)
    if pii:
        parts.append(pii.format(cpf=_cpf(r), tel=_phone(r), email=_email(r)))
    if r.random() < 0.35:
        parts.append(f"number {r.randint(10, 2500)}")
    text = ", ".join(p.strip() for p in parts if p.strip()) + r.choice(CLOSINGS)
    return _noise(text, r)


def main() -> None:
    r = random.Random(SEED)
    rows = []
    for category in TEMPLATES:
        seen: set[str] = set()
        while len(seen) < PER_CATEGORY:
            seen.add(generate_report(category, r))
        # sorted(): set order changes between runs; sorting keeps the file reproducible
        rows += [{"text": t, "category": category, "source": "synthetic"} for t in sorted(seen)]
    r.shuffle(rows)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["text", "category", "source"])
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} synthetic reports saved to {OUTPUT}")


if __name__ == "__main__":
    main()
