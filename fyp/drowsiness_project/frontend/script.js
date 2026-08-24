const WS_URL = `ws://${window.location.hostname}:8000/ws/stream`;
const API_BASE = `http://${window.location.hostname}:8000`;

const statusEl = document.getElementById("conn-status");
const videoEl = document.getElementById("video-frame");
const kssScoreEl = document.getElementById("kss-score");
const kssLabelEl = document.getElementById("kss-label");
const kssSourceEl = document.getElementById("kss-source");
const probFill = document.getElementById("prob-bar-fill");
const probValue = document.getElementById("prob-value");
const alertBanner = document.getElementById("alert-banner");
const incidentsBody = document.querySelector("#incidents-table tbody");
const incidentsEmpty = document.getElementById("incidents-empty");
const criticalFlash = document.getElementById("critical-flash");
const soundToggleBtn = document.getElementById("sound-toggle");
const downloadBtn = document.getElementById("download-csv");

// ---------------------------------------------------------------------------
// Alarm system: Web Audio API tones, generated in-browser (no audio files
// needed). Three distinct, escalating sounds so the driver can tell the
// severity apart without looking at the screen.
// ---------------------------------------------------------------------------
let audioCtx = null;
let soundEnabled = true;

function ensureAudioContext() {
  if (!audioCtx) {
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  }
  if (audioCtx.state === "suspended") {
    audioCtx.resume();
  }
  return audioCtx;
}

function beep(freq, durationMs, startDelayMs = 0, volume = 0.25, type = "sine") {
  if (!soundEnabled) return;
  const ctx = ensureAudioContext();
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.type = type;
  osc.frequency.value = freq;
  gain.gain.value = volume;
  osc.connect(gain);
  gain.connect(ctx.destination);
  const startTime = ctx.currentTime + startDelayMs / 1000;
  osc.start(startTime);
  gain.gain.setValueAtTime(volume, startTime);
  gain.gain.exponentialRampToValueAtTime(0.001, startTime + durationMs / 1000);
  osc.stop(startTime + durationMs / 1000 + 0.02);
}

function playNudgeTone() {
  beep(660, 180, 0, 0.15);
}

function playWarningTone() {
  beep(720, 160, 0, 0.22);
  beep(720, 160, 260, 0.22);
}

function playCriticalSiren() {
  // alternating two-tone siren, ~3 seconds, like an alarm klaxon
  for (let i = 0; i < 6; i++) {
    beep(880, 260, i * 300, 0.3, "square");
    beep(560, 260, i * 300 + 150, 0.3, "square");
  }
}

soundToggleBtn.addEventListener("click", () => {
  soundEnabled = !soundEnabled;
  ensureAudioContext();
  soundToggleBtn.textContent = soundEnabled ? "🔊 Sound On" : "🔇 Sound Off";
  soundToggleBtn.classList.toggle("muted", !soundEnabled);
});

// ---------------------------------------------------------------------------
// Chart
// ---------------------------------------------------------------------------
const kssChart = new Chart(document.getElementById("kss-chart"), {
  type: "line",
  data: {
    labels: [],
    datasets: [{
      label: "KSS (Karolinska Sleepiness Scale)",
      data: [],
      borderColor: "#35d0ba",
      backgroundColor: "rgba(53,208,186,0.15)",
      tension: 0.3,
      fill: true,
      pointRadius: 0,
    }],
  },
  options: {
    animation: false,
    scales: {
      y: { min: 1, max: 9, ticks: { color: "#7d8ea3" }, grid: { color: "#1f2b38" } },
      x: { display: false },
    },
    plugins: { legend: { labels: { color: "#7d8ea3" } } },
  },
});

// ---------------------------------------------------------------------------
// WebSocket
// ---------------------------------------------------------------------------
function connect() {
  const ws = new WebSocket(WS_URL);

  ws.onopen = () => {
    statusEl.textContent = "Live";
    statusEl.className = "status connected";
  };

  ws.onclose = () => {
    statusEl.textContent = "Disconnected — retrying…";
    statusEl.className = "status disconnected";
    setTimeout(connect, 1500);
  };

  ws.onerror = () => ws.close();

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.error) {
      alertBanner.textContent = data.error;
      return;
    }
    updateVideo(data);
    updateMetrics(data.frame_metrics || {});
    updateFusion(data.fusion);
    updateAlert(data.alert);
  };
}

function updateVideo(data) {
  if (data.frame_jpeg_b64) {
    videoEl.src = `data:image/jpeg;base64,${data.frame_jpeg_b64}`;
  }
}

function updateMetrics(m) {
  document.getElementById("m-ear").textContent =
    m.left_ear != null ? `${m.ear} (${m.left_ear} / ${m.right_ear})` : (m.ear ?? "--");
  document.getElementById("m-mar").textContent = m.mar ?? "--";
  document.getElementById("m-perclos").textContent = m.perclos ?? "--";
  document.getElementById("m-pitch").textContent = m.head_pitch_deg != null ? `${m.head_pitch_deg}°` : "--";
}

function updateFusion(fusion) {
  if (!fusion) return;
  kssScoreEl.textContent = fusion.kss_now;
  kssLabelEl.textContent = fusion.kss_label;
  kssSourceEl.textContent = fusion.score_source === "lstm_fusion"
    ? "predictive fusion model" : "rule-based baseline (warming up model buffer)";
  kssScoreEl.style.color = fusion.is_critical ? "#ff4d4f" : (fusion.kss_now >= 6 ? "#f5a623" : "#35d0ba");

  if (fusion.p_critical_soon != null) {
    const pct = Math.round(fusion.p_critical_soon * 100);
    probFill.style.width = `${pct}%`;
    probValue.textContent = `${pct}%`;
  } else {
    probFill.style.width = "0%";
    probValue.textContent = "model warming up…";
  }

  const chartLabels = kssChart.data.labels;
  const chartData = kssChart.data.datasets[0].data;
  chartLabels.push("");
  chartData.push(fusion.kss_now);
  if (chartLabels.length > 60) { chartLabels.shift(); chartData.shift(); }
  kssChart.update();
}

let lastAlertTimestamp = null;

function updateAlert(alert) {
  if (!alert || alert.timestamp === lastAlertTimestamp) return;
  lastAlertTimestamp = alert.timestamp;

  alertBanner.textContent = alert.message;
  alertBanner.className = `alert-banner alert-${alert.tier}`;

  if (alert.tier === "nudge") playNudgeTone();
  if (alert.tier === "warning") playWarningTone();
  if (alert.tier === "critical") {
    playCriticalSiren();
    flashCritical();
  }

  refreshIncidents();
}

function flashCritical() {
  criticalFlash.classList.add("active");
  setTimeout(() => criticalFlash.classList.remove("active"), 3200);
}

// ---------------------------------------------------------------------------
// Incident log + CSV export
// ---------------------------------------------------------------------------
async function refreshIncidents() {
  try {
    const res = await fetch(`${API_BASE}/api/incidents`);
    const json = await res.json();
    const rows = json.incidents.slice().reverse().slice(0, 30);

    incidentsBody.innerHTML = "";
    incidentsEmpty.style.display = rows.length === 0 ? "block" : "none";
    downloadBtn.disabled = json.incidents.length === 0;

    rows.forEach((inc) => {
      const tr = document.createElement("tr");
      const time = new Date(inc.timestamp * 1000).toLocaleTimeString();
      tr.innerHTML = `<td>${time}</td><td class="tier-${inc.tier}">${inc.tier}</td>` +
                      `<td>${inc.kss_now}</td><td>${inc.message}</td>`;
      incidentsBody.appendChild(tr);
    });
  } catch (e) {
    console.warn("Could not refresh incidents", e);
  }
}

downloadBtn.addEventListener("click", () => {
  const a = document.createElement("a");
  a.href = `${API_BASE}/api/incidents/csv`;
  a.download = "neuradrive_incident_log.csv";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
});

connect();
refreshIncidents();
setInterval(refreshIncidents, 10000);
