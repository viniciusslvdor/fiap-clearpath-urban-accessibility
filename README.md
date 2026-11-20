# FIAP - Faculdade de Informática e Administração Paulista

<p align="center">
<a href= "https://www.fiap.com.br/"><img src="assets/logo-fiap.png" alt="FIAP - Faculdade de Informática e Admnistração Paulista" border="0" width=40% height=40%></a>
</p>

<br>

# ClearPath: accessibility barriers, reported and resolved

## Members:
- Vinicius Salvador

## Professors:
### Tutor
- Leonardo Ruiz Orabona
### Coordinator
- André Godoi


## Description

**Global Solution 2026.2 · CitizenTech: citizen-centered technology.**

Brazil's 2022 Census (IBGE) counted **14.4 million people with disabilities** (7.3% of the population aged 2 or older). Although 84% of residents live on streets with sidewalks, only **18.8%** live on streets with obstacle-free sidewalks, and **68.8%** live on streets without wheelchair ramps. Today, someone who runs into a barrier has to find out alone which agency is responsible, fill in long forms and wait with no deadline and no feedback. On the public side, complaints arrive unstructured, repeated and without priority.

**ClearPath** is a proof of concept that lets citizens report an accessibility barrier in their own words (typed or spoken), with an optional photo and location, and automates the whole path to the responsible agency:

1. **Data governance (LGPD, Brazil's data protection law):** no sign-up; CPF (Brazilian taxpayer ID), phone, e-mail, license plate and name are masked before storage; photo EXIF is removed; GPS precision is reduced to ~11 m; every processing step is audited; citizens can erase their data with the protocol number.
2. **NLP:** classifies the report into 6 categories (word + character TF-IDF with Logistic Regression), extracts the address and computes an explainable urgency score.
3. **Computer vision (OpenCV):** estimates sidewalk damage from the photo with CLAHE, black-hat morphology, Hough-based removal of paving joints and pothole segmentation.
4. **Process automation (RPA):** groups reports about the same barrier, sets priority and deadline, writes the letter to the right agency and a daily robot escalates missed deadlines to the Ombudsman.
5. **IoT:** the *Ramp Sentinel* (ESP32 + HC-SR04, simulated on Wokwi) detects cars parked in front of ramps and publishes over MQTT; a button lets a person confirm the blockage. Node-RED shows the sensor dashboard.
6. **React:** accessible web app (voice dictation, high contrast, adjustable font size), barrier map and impact dashboard.

**Who benefits:** people with disabilities, elderly people, pregnant women and people pushing strollers, plus the maintenance teams, which receive cases already classified, prioritized and geolocated. **SDGs:** 11 (targets 11.2 and 11.7), 10 (target 10.2) and 16 (target 16.6).

**Tested results:**

| Component | Result | Basis |
|---|---|---|
| Report classifier | Macro F1 **0.90**, accuracy **90.0%** | blind test, 60 hand-written sentences |
| Automatic triage (confidence ≥ 0.50) | 57/60 forwarded automatically, **91.2%** correct | blind test |
| Computer vision | **86.7%** accuracy (3 damage levels) | 45 **synthetic** test images |
| Automated tests | **39 passing** | `pytest` |
| End-to-end MQTT | 4/4 messages processed | public HiveMQ broker |

The training data and sidewalk images are **synthetic**, and the dashboard uses **simulated** dates and agency responses; all of this is identified in [`src/data/README.md`](src/data/README.md). The letters are `.eml` files generated locally and are not sent to real agencies.

**Links:**
- Wokwi simulation: [https://wokwi.com/projects/481174110278029313](https://wokwi.com/projects/481174110278029313)


## Folder structure

Among the files and folders present in the root of the project, the following are defined:

- <b>assets</b>: contains the files related to unstructured elements of this repository, such as images.
  - `charts/`: evaluation charts (model comparison, confusion matrix, damage index, vision pipeline steps).
  - `screenshots/`: screenshot of the React app (report submission result).

- <b>docs</b>: contains all the project documents requested throughout the activities. In the "other" subfolder, add complementary and less important documents.
  - `architecture.md`, `data_governance.md`.
  - `other/evidence/`: metrics (JSON/CSV), blind-test errors and the full `pytest` output.

- <b>notebooks</b>: Jupyter notebooks, already executed.
  - `results_overview.ipynb`: **quickest way to see every result**. It shows a summary table, NLP and vision metrics, the test counts and a live run of the whole pipeline (report → letter → grouping → IoT → escalation → erasure) on a temporary database.
  - `nlp_vision_analysis.ipynb`: step-by-step explanation of the NLP and computer vision techniques.

- <b>src</b>: all the source code created for the development of the project.
  - `backend/`: `clearpath` Python package (FastAPI API, NLP, vision, governance, routing, IoT), `scripts/` (data generation, training, evaluation, SLA robot, demo data, sensor simulator), `tests/` and the trained model.
  - `frontend/`: React app (Vite, Leaflet, Recharts).
  - `iot/`: ESP32 firmware and circuit for Wokwi, Node-RED flow and [instructions](src/iot/README.md).
  - `data/`: datasets and agency table, with a [README](src/data/README.md) describing origin and limitations. `data/runtime/` (database, photos, letters) is created at runtime and kept out of Git.

- <b>pyproject.toml</b> and <b>uv.lock</b>: Python dependencies, managed with [uv](https://docs.astral.sh/uv/). `uv.lock` pins the exact versions that were tested; `.python-version` selects Python 3.13.

- <b>README.md</b>: file that serves as a guide and general explanation about the project (the one you are currently reading).

## How to run the code

**Prerequisites:** [uv](https://docs.astral.sh/uv/getting-started/installation/) (it installs Python 3.13 by itself if needed), Node.js 18+ (tested with 22) and a modern browser. Optional: a Wokwi account and Node-RED.

```bash
# 1) Backend
uv sync                                         # creates .venv with the exact versions from uv.lock

cd src/backend
uv run python scripts/generate_dataset.py       # synthetic report dataset
uv run python scripts/train_model.py            # trains, evaluates and saves the model + charts
uv run python scripts/generate_demo_images.py   # synthetic sidewalk images
uv run python scripts/evaluate_vision.py test   # evaluates the computer vision module
uv run python scripts/seed_demo.py              # demo data for the dashboard
uv run pytest -v                                # 39 tests

uv run uvicorn clearpath.api:app --port 8000    # API → http://localhost:8000/docs
```

```bash
# 2) Frontend (another terminal)
cd src/frontend
npm install
npm run dev                                     # → http://localhost:5173
```

```bash
# 3) IoT (another terminal, from src/backend)
uv run python -m clearpath.mqtt_bridge          # subscribes to MQTT and creates reports
uv run python scripts/simulate_sensor.py        # (optional) simulates the ESP32 without Wokwi
uv run python scripts/sla_robot.py              # robot: escalates missed deadlines, applies retention, writes the report
```

To see all results without starting the servers, open `notebooks/results_overview.ipynb` (already executed) or run it again with `uv run jupyter notebook` from `notebooks/`.

ESP32 on Wokwi and Node-RED: see [`src/iot/README.md`](src/iot/README.md).



## Release history

* 1.0.0 - 2026-11-19
    * First complete version of the ClearPath POC: FastAPI backend, NLP classifier, computer vision, process automation, ESP32/MQTT sensor, React app and notebooks.

## License

<img style="height:22px!important;margin-left:3px;vertical-align:text-bottom;" src="https://mirrors.creativecommons.org/presskit/icons/cc.svg?ref=chooser-v1"><img style="height:22px!important;margin-left:3px;vertical-align:text-bottom;" src="https://mirrors.creativecommons.org/presskit/icons/by.svg?ref=chooser-v1"><p xmlns:cc="http://creativecommons.org/ns#" xmlns:dct="http://purl.org/dc/terms/"><a property="dct:title" rel="cc:attributionURL" href="https://github.com/agodoi/template">FIAP GIT MODEL</a> by <a rel="cc:attributionURL dct:creator" property="cc:attributionName" href="https://fiap.com.br">Fiap</a> is licensed under <a href="http://creativecommons.org/licenses/by/4.0/?ref=chooser-v1" target="_blank" rel="license noopener noreferrer" style="display:inline-block;">Attribution 4.0 International</a>.</p>
