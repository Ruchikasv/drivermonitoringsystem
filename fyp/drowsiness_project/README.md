# NeuraDrive — Predictive Multi-Modal Driver State Intelligence System

An advanced, laptop-only driver drowsiness detection system built for a
5-member team  project. Unlike the typical "webcam + eye-closure +
beep" clones on GitHub, this fuses **vision (EAR/MAR/PERCLOS) and head
pose** signals through a temporal LSTM that **predicts** fatigue trend on
the **Karolinska Sleepiness Scale (KSS)** — the same scale Euro NCAP's 2026
protocol uses to grade production drowsiness systems — instead of just
reacting to closed eyes. It ships with a live FastAPI + WebSocket backend,
a browser dashboard with a real audio alarm system and CSV incident export,
and a documented methodology notebook.

This build uses **only visual/behavioral signals** — no heart-rate or other
physiological sensing anywhere in the project.

---

## What changed in this version (bug fixes from real testing)

Two real bugs were found running this on an actual webcam and are fixed:

1. **Head pose wraparound bug**: a front-facing head was reading pitch as
   `-177.5°` instead of `~0°`, because `cv2.decomposeProjectionMatrix` has a
   known wraparound quirk. Fixed by wrapping all angles into `[-90, 90]`
   (`backend/core/head_pose.py`, `_wrap_to_90`).
2. **False microsleep alerts from head turns**: averaging both eyes' EAR
   meant one occluded/misread eye (e.g. while looking to the side) could
   drag the average below the closed-eye threshold and fire a false
   CRITICAL alert. Fixed by requiring **both eyes individually** closed,
   sustained for a real duration in seconds (not a frame count, which
   behaves differently depending on how fast your machine processes
   frames) — see `backend/core/event_detectors.py`.

Both fixes are demonstrated with before/after code in the notebook
(`notebooks/01_methodology_and_demo.ipynb`, sections 3 and 4).

---

## Do we need a dataset?

**Short answer: no, not to run this project.**

| Component | Needs a labeled dataset? | Why |
|---|---|---|
| Face landmark detection (EAR/MAR/head pose) | No | Uses Google's pretrained MediaPipe FaceLandmarker model — downloaded automatically on first run. |
| PERCLOS / blink / microsleep / yawn logic | No | Geometry/threshold + duration logic on the landmarks, not learned. |
| **FatigueLSTM (the predictive fusion model)** | **Optional** | Ships **already trained** on a physiologically-realistic **synthetic dataset generated inside the project** (`backend/train/train_synthetic.py`). Works out of the box. |

The project runs with **zero dataset downloads**. If you want to retrain
the FatigueLSTM on real human sessions instead of synthetic ones (a good
"future work" slide, not required for the demo):

- **NTHU-DDD** — https://cv.cs.nthu.edu.tw/php/callforpaper/datasets/DDD/
- **UTA-RLDD** — https://sites.google.com/view/utarldd/home
- **YawDD** — https://www.site.uottawa.ca/~shervin/yawning/

All three require a short academic-use request form (not direct-download
links) — normal for face-video datasets. Not needed to run the demo.

---

## What's novel here (for our pitch)

1. **Multi-modal fusion, not single-signal**: eye closure + blink pattern +
   yawning + head pose, fused together over time — not one signal.
2. **Predictive, not reactive**: the LSTM forecasts *probability of
   reaching critical fatigue in the next 5 minutes*, not just "eyes closed
   now."
3. **Regulation-aligned scoring**: output is calibrated to the Karolinska
   Sleepiness Scale (1–9), the exact scale the EU's Euro NCAP 2026 protocol
   grades drowsiness systems against.
4. **Real tiered alarm system**: distinct in-browser audio tones (soft
   nudge → double-beep warning → loud siren + full-screen flash for
   critical) generated live with the Web Audio API, plus simulated
   GPS-tagged SOS logging.
5. **CSV incident export**: one click downloads every logged drowsiness
   event this session as a CSV — the kind of audit trail a real fleet
   dashboard would need.
6. **Privacy-by-design**: all processing is local/on-device — no video ever
   leaves the laptop.
7. **Robustness fixes baked in**: both-eye + duration-based event
   detection avoids the false positives that plague single-signal,
   frame-count-based clones (see "What changed" above).

---

## Project structure

```
drowsiness_project/
├── backend/
│   ├── app.py                      # FastAPI app: webcam loop, WebSocket stream, REST + CSV API
│   ├── requirements.txt
│   ├── core/
│   │   ├── config.py                # all tunable thresholds live here
│   │   ├── face_mesh.py              # MediaPipe FaceLandmarker wrapper
│   │   ├── ear_mar.py                # EAR / MAR geometry
│   │   ├── perclos.py                # PERCLOS + blink tracking
│   │   ├── head_pose.py              # solvePnP head pose (with wraparound fix)
│   │   ├── event_detectors.py        # time-based sustained-condition detector (microsleep/yawn/nod)
│   │   ├── fusion_engine.py          # aggregates signals, runs the LSTM
│   │   ├── kss_mapper.py             # rule-based KSS scoring + labels
│   │   └── alert_manager.py          # tiered alerts, incident logging, SOS
│   ├── models/
│   │   ├── fatigue_lstm.py           # PyTorch LSTM model definition (6 input features)
│   │   └── fatigue_lstm_weights.pt   # pretrained weights (already included)
│   ├── train/
│   │   └── train_synthetic.py        # synthetic data generator + training script
│   └── tests_sandbox_validation.py   # unit tests, incl. regression tests for both bug fixes
├── frontend/
│   ├── index.html                    # dashboard
│   ├── style.css
│   └── script.js                     # WebSocket client, Web Audio alarms, CSV download
├── notebooks/
│   └── 01_methodology_and_demo.ipynb # full math + methodology + bug-fix demos (already executed)
├── logs/
│   └── incidents.jsonl               # created at runtime, alert history
└── README.md                         # this file
```

---

## How to run on Mac (VS Code)

### 1. Prerequisites
- macOS with a working webcam
- Python 3.10–3.12
- VS Code with the Python extension

### 2. Unzip and open in VS Code
```bash
unzip neuradrive_project.zip -d neuradrive
cd neuradrive/drowsiness_project
code .
```

### 3. Create a virtual environment
```bash
python3 -m venv venv
source venv/bin/activate
```
In VS Code: `Cmd+Shift+P` → "Python: Select Interpreter" → choose the
`venv` one.

### 4. Install dependencies
```bash
cd backend
pip install -r requirements.txt
```

### 5. Run the backend
```bash
python -m uvicorn app:app --reload --host 0.0.0.0 --port 8000
```
**Important: use `python -m uvicorn`, not a bare `uvicorn` command.** A
bare `uvicorn` can resolve to a *different* Python install than your active
venv (this exact issue came up in testing — `uvicorn app:app` raised
`ModuleNotFoundError: No module named 'cv2'` even though `cv2` was
installed in the venv, because the `uvicorn` on PATH belonged to a
different interpreter). `python -m uvicorn` always uses the currently
active environment.

- First run auto-downloads the MediaPipe face model (~4 MB, needs internet
  once) into `backend/models/face_landmarker.task`.
- macOS will prompt for **camera permission** — click Allow (or check
  System Settings → Privacy & Security → Camera).
- The trained fusion model is already included — no training step needed
  to run the live demo.

### 6. Open the dashboard
Go to **http://localhost:8000**. You'll see your live camera feed with
landmark overlay, EAR/MAR/PERCLOS/head-pitch readouts, the live KSS gauge
and trend chart, and the alert panel.

### 7. Try the alarm system
- The 🔊 **Sound On/Off** button in the header toggles the alarm; click it
  once so your browser allows audio playback (browsers require a user
  click before audio can play).
- Fatigue-mimicking behavior in front of the camera (slow heavy blinks,
  closing both eyes for ~1 second, yawning, or nodding your head forward)
  will escalate through nudge → warning → critical, each with a distinct
  sound, and critical also flashes the screen red.

### 8. Download the incident log
Click **⬇ Download Incident Log (CSV)** in the Incident Log panel — it
downloads every logged drowsiness event this session (timestamp, tier,
KSS score, message, simulated GPS, SOS status) as
`neuradrive_incident_log.csv`. Also available directly at
`http://localhost:8000/api/incidents/csv`.

### 9. (Optional) Explore the methodology notebook
```bash
pip install jupyter
jupyter notebook ../notebooks/01_methodology_and_demo.ipynb
```
Already executed with all plots/output saved in, including live
demonstrations of both bug fixes.

### 10. (Optional) Retrain the fusion model
```bash
cd backend/train
python3 train_synthetic.py
```
Takes about a minute on a laptop CPU.

---

## How to run on Windows

Same steps, only the venv commands differ:
```powershell
python -m venv venv
venv\Scripts\activate
cd backend
pip install -r requirements.txt
python -m uvicorn app:app --reload --host 0.0.0.0 --port 8000
```
Check **Settings → Privacy & Security → Camera** and enable "Let apps
access your camera" / "Let desktop apps access your camera" if the feed
doesn't show up.

---

## Configuration

All thresholds live in `backend/core/config.py`: EAR sensitivity,
microsleep/yawn/head-nod durations, PERCLOS windows, alert cooldowns, KSS
critical threshold, and email/SOS settings. To enable real SOS emails, set
`ENABLE_EMAIL_SOS = True` and fill in a Gmail address + an
[App Password](https://myaccount.google.com/apppasswords).

---

## Known limitations (be upfront in Q&A — judges respect this)

- **FatigueLSTM trained on synthetic data**: physiologically realistic but
  not real human sessions. Architecture and training loop are ready to
  retrain on NTHU-DDD/UTA-RLDD/YawDD without code changes.
- **Single driver, laptop demo**: no vehicle actuator integration (steering
  haptics, adaptive cruise) — simulated/logged, with the integration point
  isolated in `alert_manager.py` for a team with hardware access to extend.
- **GPS is simulated** (`config.SIMULATED_GPS_LAT/LON`) — no GPS hardware
  on a laptop.
- **Lighting-dependent**: like all camera-based systems, very low light or
  strong backlighting (e.g. sitting in front of a bright window) can
  degrade landmark accuracy.

---

## 5-person team ownership split (suggested)

1. **CV lead** — `face_mesh.py`, `ear_mar.py`, `head_pose.py`
2. **Signal/pattern lead** — `perclos.py`, `event_detectors.py`, threshold tuning
3. **ML lead** — `fusion_engine.py`, `fatigue_lstm.py`, `train_synthetic.py`
4. **Systems lead** — `app.py`, `alert_manager.py`, incident logging, CSV export, SOS
5. **Frontend/demo lead** — `frontend/` (dashboard + alarm sound design), notebook polish, pitch deck
