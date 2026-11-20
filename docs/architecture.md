# ClearPath architecture

## Overview

```mermaid
flowchart LR
    subgraph Citizen
        APP[React web app<br/>text, voice, photo, map]
    end
    subgraph Street
        ESP[ESP32 + HC-SR04<br/>Ramp Sentinel]
    end
    ESP -- MQTT JSON --> BROKER[(MQTT broker<br/>HiveMQ)]
    BROKER --> BRIDGE[MQTT bridge<br/>Python / paho]
    BROKER --> NR[Node-RED<br/>sensor dashboard]
    APP -- REST / JSON --> API[FastAPI API]
    BRIDGE --> SERV
    API --> SERV[Report service]
    SERV --> GOV[Governance<br/>anonymization, hash, EXIF]
    SERV --> NLP[NLP<br/>TF-IDF + Logistic Regression,<br/>urgency, address]
    SERV --> CV[Computer vision<br/>OpenCV: CLAHE, black-hat,<br/>Hough, segmentation]
    SERV --> ROUT[Automation<br/>routing, SLA, grouping]
    ROUT --> EML[[.eml letters<br/>to the agencies]]
    SERV --> DB[(SQLite<br/>reports, history,<br/>audit log, IoT)]
    ROBOT[Scheduled SLA robot] --> DB
    ROBOT --> EML
    ROBOT --> REP[[Daily report<br/>CSV + HTML]]
    API --> DASH[Impact dashboard<br/>and map in React]
```

## Automated process (simplified BPMN)

```mermaid
flowchart TD
    A([Report arrives: app or sensor]) --> B[Anonymize text, remove EXIF,<br/>reduce GPS precision]
    B --> C{Same text in<br/>the last 24 h?}
    C -- yes --> C1([Return the existing protocol])
    C -- no --> D[Classify category + score urgency]
    D --> E{Photo?}
    E -- yes --> E1[Damage index via computer vision]
    E -- no --> F
    E1 --> F{Someone already reported<br/>the same barrier within 60 m?}
    F -- yes --> F1[Group and raise the priority<br/>of the original occurrence]
    F -- no --> G
    F1 --> G[Compute priority and SLA deadline]
    G --> H{Classifier<br/>confidence ≥ 0.50?}
    H -- no --> H1([Human triage])
    H -- yes --> I[Generate .eml letter to the responsible agency]
    I --> J([Forwarded])
    J --> K{Daily robot: deadline missed<br/>without resolution?}
    K -- yes --> L[Letter to the Ombudsman + escalated status]
    K -- no --> M([Agency updates via PATCH:<br/>in progress / resolved])
```

## Sequence: ramp sensor

```mermaid
sequenceDiagram
    participant S as ESP32 (Wokwi)
    participant B as MQTT broker
    participant P as Python bridge
    participant R as ClearPath
    S->>S: distance < 80 cm for 10 s
    S->>B: {"event":"obstruction", ...}
    B->>P: message
    P->>R: process_message()
    R->>R: creates report (source iot) + letter
    Note over S: a person presses the blue button
    S->>B: {"event":"confirmation"}
    B->>P: message
    P->>R: +15 urgency points on the same report
    S->>B: {"event":"cleared"} (after 5 s clear)
    P->>R: records it in the history (does not close the case by itself)
```

## Code structure

| Module | Responsibility |
|---|---|
| `src/backend/clearpath/governance.py` | Anonymization (CPF, phone, e-mail, plate, name), pseudonymization, GPS precision |
| `src/backend/clearpath/nlp.py` | Preprocessing, classification, explainable urgency, address extraction |
| `src/backend/clearpath/vision.py` | OpenCV pipeline and damage index |
| `src/backend/clearpath/routing.py` | Priority, SLA, distance-based grouping (Haversine), letters, escalation |
| `src/backend/clearpath/service.py` | Orchestrates the pipeline; right to erasure; retention |
| `src/backend/clearpath/iot.py`, `mqtt_bridge.py` | Sensor events and MQTT subscription |
| `src/backend/clearpath/api.py` | REST API (FastAPI, Swagger at `/docs`) |
| `src/backend/scripts/` | Data generation, training, evaluation, SLA robot, demo data, sensor simulator |
| `src/frontend/` | React app (Vite, Leaflet, Recharts) |
| `src/iot/wokwi/` | ESP32 firmware + Wokwi circuit |
| `src/iot/node-red/` | Node-RED flow (sensor dashboard) |

## API endpoints

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/health` | Checks that the API and the model are up |
| GET | `/api/categories` | Categories, responsible agency and legal basis |
| POST | `/api/classify` | Classification preview, nothing stored (used while typing) |
| POST | `/api/reports` | Creates a report (multipart: text, consent, lat, lon, photo) |
| GET | `/api/reports` | List (filters: category, status, priority) |
| GET | `/api/reports/{protocol}` | Details + timeline |
| PATCH | `/api/reports/{protocol}/status` | The agency updates the progress |
| DELETE | `/api/reports/{protocol}/data` | Right to erasure (LGPD art. 18) |
| POST | `/api/automation/escalate` | Triggers the escalation of missed deadlines |
| POST | `/api/iot/readings` | HTTP alternative to MQTT |
| GET | `/api/iot/devices` | Sensor states |
| GET | `/api/indicators` | Impact indicators (SDGs) |
