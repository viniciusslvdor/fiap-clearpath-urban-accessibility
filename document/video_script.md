# Video script (up to 5 minutes)

> Record the screen in 1080p. Before recording: `uv run python scripts/seed_demo.py`, then start the API, the MQTT bridge and the frontend, and keep Wokwi open in another tab.
> Upload to YouTube as **Unlisted** and paste the link into the PDF and the README.

| Time | Speaker | Screen | Talking points |
|---|---|---|---|
| 0:00–0:15 | Vinicius | Camera or title slide | "I am Vinicius Salvador, and this is ClearPath, my Global Solution 2026.2 project." |
| 0:15–0:50 | Vinicius | Slide with the IBGE numbers | The problem: 14.4 million people with disabilities in Brazil; only 18.8% live on streets with obstacle-free sidewalks; 68.8% on streets without ramps. Today, complaining is hard and there is no deadline for an answer. SDGs 10 and 11. |
| 0:50–1:20 | Vinicius | Architecture diagram (`document/architecture.md`) | Overview: React → FastAPI API → anonymization → NLP → vision → automation → agency. ESP32 sensor over MQTT. Name the integrated disciplines. |
| 1:20–2:20 | Vinicius | App: Report tab | Type a report with a CPF on purpose. Show the live preview (category, priority, personal data warning). Mark the map, attach `severe_03.jpg`, submit. Show the protocol, the reason for the priority and the photo with cracks and potholes highlighted. |
| 2:20–2:50 | Vinicius | Track tab + `src/data/runtime/letters` folder | Timeline; open the `.eml` automatically generated for the Subprefecture. Show the delete-data button (LGPD). |
| 2:50–3:40 | Vinicius | Wokwi + bridge terminal + Dashboard | Drag the HC-SR04 distance to 40 cm, wait for the red LED, show the message on the Serial Monitor, the bridge log and the "blocked" sensor on the Dashboard. Press the blue button (confirmation). |
| 3:40–4:20 | Vinicius | Impact dashboard + evidence | Indicators (say the data is simulated), confusion matrix: F1 = 0.90 on the blind test, vision at 86.7%. Run `pytest` (39 tests passing). |
| 4:20–4:55 | Vinicius | Final slide | Limitations (synthetic data, public broker, no face blurring) and next steps (real pilot with a subprefecture). How to measure impact. Thanks. |

## Integration between disciplines (say it explicitly in the video)

- **Process automation / RPA / REST APIs:** automatic routing, `.eml` letters, deadline robot and FastAPI API.
- **Front-end with React:** accessible app (voice, high contrast, adjustable font size, map).
- **NLP:** preprocessing, TF-IDF, classification, address extraction and urgency.
- **Computer vision:** CLAHE, Gaussian filter, black-hat, thresholding, Hough and segmentation.
- **IoT:** ESP32, HC-SR04, MQTT and Node-RED.
- **Data governance:** LGPD, anonymization, audit log, retention and quality.
