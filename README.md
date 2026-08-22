# Intelligent Driver Monitoring and Fleet Safety Management System

## Phase 1 — Driver Facial Authentication

A local, privacy-first driver authentication system using facial recognition.
The system captures a driver's face via the laptop webcam, generates a
biometric embedding using **InsightFace (ArcFace)**, and stores it in a local
**SQLite** database. During authentication, the live face is compared against
all registered drivers to identify the person.

> **Privacy Notice:** Face embeddings are biometric data. The database file
> (`data/drivers.db`) should be treated as sensitive and must not be committed
> to version control or shared publicly.

---

## Features

- **Driver Registration** — Multi-frame face capture with averaged embeddings
  for robustness.
- **Driver Authentication** — Real-time face recognition with configurable
  similarity threshold.
- **Duplicate Detection** — Warns if a face is already registered during
  enrollment.
- **Local Processing** — All inference runs locally via ONNX. No data is sent
  to external servers.
- **Modular Architecture** — Clean separation of camera, face recognition,
  database, and configuration layers.

---

## Tech Stack

| Component           | Technology                       |
|---------------------|----------------------------------|
| Language            | Python 3.11                      |
| Face Detection      | InsightFace (RetinaFace)         |
| Face Recognition    | InsightFace (ArcFace, 512-d)     |
| Inference Runtime   | ONNX Runtime                     |
| Webcam Capture      | OpenCV                           |
| Database            | SQLite                           |
| Testing             | pytest                           |

---

## Project Structure

```
driver-monitoring/
├── app/
│   ├── config/
│   │   └── settings.py             # All configurable constants
│   ├── camera/
│   │   └── capture.py              # WebcamCapture context manager
│   ├── face_recognition/
│   │   ├── detector.py             # InsightFace wrapper
│   │   └── comparator.py           # Embedding matching logic
│   └── database/
│       ├── connection.py           # SQLite connection + schema
│       └── driver_repository.py    # Driver CRUD operations
├── scripts/
│   ├── register_driver.py          # CLI: register a driver
│   └── authenticate_driver.py      # CLI: authenticate a driver
├── models/                         # InsightFace model cache (git-ignored)
├── data/                           # SQLite database (git-ignored)
├── tests/
│   ├── test_database.py
│   └── test_comparator.py
├── requirements.txt
├── README.md
└── .gitignore
```

---

## Setup

### Prerequisites

- Python 3.11 or later
- A laptop with a built-in webcam (or USB webcam)
- ~400 MB disk space for model weights (downloaded on first run)

### Installation

```bash
# 1. Clone the repository
git clone <repo-url>
cd driver-monitoring

# 2. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

# 3. Install dependencies
pip install -r requirements.txt
```

### First Run — Model Download

On the first run of any face-detection feature, InsightFace will
automatically download the **buffalo_l** model pack (~300 MB) into the
`models/` directory. Ensure you have an internet connection for this
one-time download.

---

## Usage

### Register a Driver

```bash
python scripts/register_driver.py
```

1. Enter the driver's name when prompted.
2. The webcam will open with a live preview.
3. Position your face in the frame — a green bounding box confirms detection.
4. Press **SPACE** to begin capturing face samples (10 frames by default).
5. The system will average the embeddings and store the driver in the database.
6. Press **Q** at any time to cancel.

### Authenticate a Driver

```bash
python scripts/authenticate_driver.py
```

1. The webcam opens with continuous face detection.
2. Detected faces are matched against all registered drivers.
3. **Green box + name** = authenticated driver.
4. **Red box + "Unknown"** = face not recognised.
5. Press **Q** to quit.

---

## Configuration

All tuneable parameters are in [`app/config/settings.py`](app/config/settings.py):

| Parameter                    | Default | Description                                           |
|------------------------------|---------|-------------------------------------------------------|
| `CAMERA_INDEX`               | `0`     | Webcam device index                                   |
| `RECOGNITION_THRESHOLD`      | `0.45`  | Minimum cosine similarity for a positive match        |
| `DETECTION_CONFIDENCE`       | `0.5`   | Minimum face detection confidence                     |
| `REGISTRATION_NUM_FRAMES`    | `10`    | Frames to capture during registration                 |
| `REGISTRATION_MIN_FRAMES`    | `5`     | Minimum good frames required                          |
| `DUPLICATE_DETECTION_THRESHOLD` | `0.55` | Similarity threshold for duplicate warnings          |
| `INSIGHTFACE_MODEL_NAME`     | `buffalo_l` | InsightFace model pack                            |

Parameters can also be overridden via environment variables (prefix `DMS_`):

```bash
set DMS_CAMERA_INDEX=1
set DMS_RECOGNITION_THRESHOLD=0.50
```

---

## Testing

```bash
python -m pytest tests/ -v
```

All tests use in-memory SQLite and synthetic embeddings — no webcam or model
weights required.

---

## Security & Privacy

- **No cloud calls** — all face analysis runs locally via ONNX Runtime.
- **No face images stored** — only 512-dimensional embeddings are persisted.
- **Embeddings are not reversible** — they cannot be converted back to photos.
- **Database is git-ignored** — `data/*.db` is excluded from version control.
- **Parameterised SQL** — all database queries use `?` placeholders.
- **Biometric data warning** — the SQLite database contains biometric data
  and should be treated as sensitive under GDPR and similar regulations.

---

## Frontend Web Dashboard

A commercial fleet safety operations dashboard built with **React**, **Vite**, **Tailwind CSS**, and **Recharts**.

### Running the Dashboard Locally

```bash
# 1. Navigate to the frontend folder
cd frontend

# 2. Start the Vite development server
npm run dev
```

Open your browser at `http://localhost:5173`.

### Dashboard Capabilities
- **Overview Dashboard (`/`)** — Real-time driver counts, today's alert metrics, fleet safety scores, circadian drowsiness trends (Recharts), and active route monitoring.
- **Drivers Directory (`/drivers`)** — Commercial driver directory connected to Phase 1 registered database (Driver #1: Ruchika) with search and status filtering.
- **Driver Dossier (`/drivers/:id`)** — Individual driver profile, trip history, sensor alerts, and safety scores.
- **Live Vehicle Stream (`/live-monitoring`)** — Operational camera preview and telemetry layout (EAR, MAR, PERCLOS, Head Pose, MQ-3 alcohol sensor status) ready for Phase 2 computer vision streaming.
- **Trip Logs (`/trips`)** — Commercial transport logs with route segments, durations, and safety incidents.
- **Alert Console (`/alerts`)** — 3-tier severity alerts (Level 1 Low, Level 2 Moderate, Level 3 Critical) with multi-criteria filtering.
- **Risk Analytics (`/analytics`)** — Fatigue risk curves, infractions by driver, safety score distribution, and rest break compliance.
- **System Settings (`/settings`)** — Configuration reference for camera index, facial recognition thresholds, and notification dispatch policies.

---

## Roadmap

This is a multi-phase system:

- **Phase 1: Driver Facial Authentication** (Completed)
- **Phase 1.5: Fleet Owner Web Dashboard** (Completed)
- **Phase 2: Real-time Drowsiness Detection & In-Cabin AI** (EAR, MAR, PERCLOS, Head Pose)
- **Phase 3: Hardware Sensor Integration** (MQ-3 Alcohol Sensor & 3-Level Audio/Visual Alert Matrix)
- **Phase 4: Backend API & Live WebSocket Streaming** (FastAPI Backend + Fleet Live Sync)

