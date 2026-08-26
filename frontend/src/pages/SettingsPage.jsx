import React, { useState, useEffect } from 'react';
import Card from '../components/common/Card';
import { Camera, Sliders, Bell, Shield, Database, Cpu, Check, Info, RefreshCw } from 'lucide-react';
import { apiClient } from '../services/api';

export default function SettingsPage() {
  const [cameraIndex, setCameraIndex] = useState('0');
  const [recognitionThreshold, setRecognitionThreshold] = useState('0.45');
  const [detectionConfidence, setDetectionConfidence] = useState('0.50');
  const [modelName, setModelName] = useState('buffalo_l');
  const [savedNotice, setSavedNotice] = useState(false);
  const [healthStatus, setHealthStatus] = useState(null);
  const [healthLoading, setHealthLoading] = useState(false);

  // Notification toggles
  const [notifLevel1, setNotifLevel1] = useState(true);
  const [notifLevel2, setNotifLevel2] = useState(true);
  const [notifLevel3, setNotifLevel3] = useState(true);
  const [soundAlerts, setSoundAlerts] = useState(true);

  const fetchHealth = async () => {
    try {
      setHealthLoading(true);
      const res = await apiClient.get('/system/health');
      setHealthStatus(res.data);
    } catch (err) {
      console.error('Failed to fetch system health:', err);
      setHealthStatus({
        status: 'degraded',
        services: {
          api: 'error',
          database: 'error',
          face_recognition: 'error',
          drowsiness_engine: 'standby',
          websocket_pipeline: 'standby',
          camera_interface: 'browser_webcam',
        }
      });
    } finally {
      setHealthLoading(false);
    }
  };

  useEffect(() => {
    fetchHealth();
  }, []);

  const handleSave = (e) => {
    e.preventDefault();
    setSavedNotice(true);
    setTimeout(() => setSavedNotice(false), 3000);
  };

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Notice */}
      <div className="p-4 rounded-xl bg-slate-100 border border-slate-200 text-xs text-slate-700 flex items-start gap-3">
        <Info className="w-4 h-4 text-slate-500 shrink-0 mt-0.5" />
        <div>
          <span className="font-bold text-slate-900 block text-xs">
            Phase 1 Backend Configuration Reference
          </span>
          <p className="mt-0.5 text-slate-600">
            Parameters below correspond to settings defined in <code className="bg-white px-1.5 py-0.5 rounded border border-slate-200 font-mono text-[11px]">app/config/settings.py</code>. In Phase 2, these can be dynamically managed through the FastAPI control plane.
          </p>
        </div>
      </div>

      {savedNotice && (
        <div className="p-3 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs flex items-center gap-2">
          <Check className="w-4 h-4 text-emerald-600 shrink-0" />
          <span>Local UI preferences updated successfully.</span>
        </div>
      )}

      <form onSubmit={handleSave} className="space-y-6">
        {/* Camera Hardware Settings */}
        <Card
          title="Camera & Hardware Interface"
          subtitle="OpenCV video capture source device configurations"
        >
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Webcam Device Index
              </label>
              <input
                type="number"
                value={cameraIndex}
                onChange={(e) => setCameraIndex(e.target.value)}
                className="w-full text-xs px-3 py-2 rounded-lg border border-slate-200 bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
              />
              <p className="text-[11px] text-slate-500 mt-1">Default 0 (Built-in laptop webcam or primary USB)</p>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Video Resolution Mode
              </label>
              <select
                disabled
                className="w-full text-xs px-3 py-2 rounded-lg border border-slate-200 bg-slate-100 text-slate-600 cursor-not-allowed"
              >
                <option>1280 × 720 (HD - 30 FPS)</option>
              </select>
              <p className="text-[11px] text-slate-500 mt-1">Managed automatically by OpenCV backend</p>
            </div>
          </div>
        </Card>

        {/* Biometrics & AI Thresholds */}
        <Card
          title="Facial Recognition & AI Parameters"
          subtitle="InsightFace ArcFace detection and verification parameters"
        >
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Recognition Cosine Threshold
              </label>
              <input
                type="number"
                step="0.01"
                min="0.1"
                max="0.9"
                value={recognitionThreshold}
                onChange={(e) => setRecognitionThreshold(e.target.value)}
                className="w-full text-xs px-3 py-2 rounded-lg border border-slate-200 bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 font-mono"
              />
              <p className="text-[11px] text-slate-500 mt-1">Currently 0.45 in settings.py (Same person: 0.5-0.8)</p>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Detection Confidence Cutoff
              </label>
              <input
                type="number"
                step="0.05"
                min="0.1"
                max="0.9"
                value={detectionConfidence}
                onChange={(e) => setDetectionConfidence(e.target.value)}
                className="w-full text-xs px-3 py-2 rounded-lg border border-slate-200 bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 font-mono"
              />
              <p className="text-[11px] text-slate-500 mt-1">Minimum RetinaFace detection score (0.50 default)</p>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                InsightFace Model Pack
              </label>
              <input
                type="text"
                disabled
                value={modelName}
                className="w-full text-xs px-3 py-2 rounded-lg border border-slate-200 bg-slate-100 text-slate-600 font-mono cursor-not-allowed"
              />
              <p className="text-[11px] text-slate-500 mt-1">buffalo_l (512-dimensional ArcFace vectors)</p>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Local Database Engine
              </label>
              <div className="flex items-center gap-2 text-xs font-mono py-2 text-slate-700">
                <Database className="w-4 h-4 text-blue-600" />
                <span>SQLite (data/drivers.db)</span>
              </div>
              <p className="text-[11px] text-slate-500">BLOB float32 serialized embeddings (2048 bytes)</p>
            </div>
          </div>
        </Card>

        {/* Drowsiness & Fatigue Detection Engine Configuration */}
        <Card
          title="Software DMS Drowsiness & Fatigue Thresholds"
          subtitle="Computer vision signal thresholds configured in app/config/settings.py"
        >
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                EAR Eye-Closure Cutoff
              </label>
              <input
                type="number"
                step="0.01"
                disabled
                value="0.21"
                className="w-full text-xs px-3 py-2 rounded-lg border border-slate-200 bg-slate-100 text-slate-600 font-mono cursor-not-allowed"
              />
              <p className="text-[11px] text-slate-500 mt-1">EAR &lt; 0.21 qualifies eye as closed (MediaPipe 478 pts)</p>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                PERCLOS Fatigue Trigger
              </label>
              <input
                type="text"
                disabled
                value="30.0% (0.30)"
                className="w-full text-xs px-3 py-2 rounded-lg border border-slate-200 bg-slate-100 text-slate-600 font-mono cursor-not-allowed"
              />
              <p className="text-[11px] text-slate-500 mt-1">Percentage of eye closure over 60s rolling window</p>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                MAR Yawn Threshold
              </label>
              <input
                type="number"
                step="0.01"
                disabled
                value="0.55"
                className="w-full text-xs px-3 py-2 rounded-lg border border-slate-200 bg-slate-100 text-slate-600 font-mono cursor-not-allowed"
              />
              <p className="text-[11px] text-slate-500 mt-1">Mouth aspect ratio sustained &gt; 1.5s triggers yawn event</p>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Head Nod Pitch Cutoff
              </label>
              <input
                type="text"
                disabled
                value="-15.0°"
                className="w-full text-xs px-3 py-2 rounded-lg border border-slate-200 bg-slate-100 text-slate-600 font-mono cursor-not-allowed"
              />
              <p className="text-[11px] text-slate-500 mt-1">Head downward nodding pitch angle limit</p>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Alert Escalation Cooldowns
              </label>
              <input
                type="text"
                disabled
                value="Nudge: 15s | Warn: 30s | Crit: 45s"
                className="w-full text-xs px-3 py-2 rounded-lg border border-slate-200 bg-slate-100 text-slate-600 font-mono cursor-not-allowed"
              />
              <p className="text-[11px] text-slate-500 mt-1">Prevents alert spam during sustained events</p>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                KSS Scale Model
              </label>
              <input
                type="text"
                disabled
                value="Euro NCAP 1.0–9.0"
                className="w-full text-xs px-3 py-2 rounded-lg border border-slate-200 bg-slate-100 text-slate-600 font-mono cursor-not-allowed"
              />
              <p className="text-[11px] text-slate-500 mt-1">Multi-modal rule & LSTM fusion sleepiness estimate</p>
            </div>
          </div>
        </Card>

        {/* Software System Health Section */}
        <Card
          title="Software System Health & Runtime Diagnostics"
          subtitle="Real-time status of backend services and model pipelines from /system/health"
        >
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 text-xs">
            <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
              <span className="text-slate-500 block text-[10px] uppercase font-bold">FastAPI Backend</span>
              <span className={`font-bold flex items-center gap-1.5 mt-1 ${healthStatus?.services?.api === 'online' ? 'text-emerald-600' : 'text-rose-600'}`}>
                <span className={`w-2 h-2 rounded-full ${healthStatus?.services?.api === 'online' ? 'bg-emerald-500 animate-pulse' : 'bg-rose-500'}`} />
                {healthStatus?.services?.api?.toUpperCase() || 'CHECKING…'}
              </span>
            </div>

            <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
              <span className="text-slate-500 block text-[10px] uppercase font-bold">SQLite Database</span>
              <span className={`font-bold flex items-center gap-1.5 mt-1 ${healthStatus?.services?.database === 'connected' ? 'text-emerald-600' : 'text-rose-600'}`}>
                <span className={`w-2 h-2 rounded-full ${healthStatus?.services?.database === 'connected' ? 'bg-emerald-500' : 'bg-rose-500'}`} />
                {healthStatus?.services?.database?.toUpperCase() || 'CHECKING…'}
              </span>
            </div>

            <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
              <span className="text-slate-500 block text-[10px] uppercase font-bold">InsightFace Model</span>
              <span className={`font-bold flex items-center gap-1.5 mt-1 ${healthStatus?.services?.face_recognition === 'ready' ? 'text-emerald-600' : 'text-amber-600'}`}>
                <span className={`w-2 h-2 rounded-full ${healthStatus?.services?.face_recognition === 'ready' ? 'bg-emerald-500' : 'bg-amber-500'}`} />
                {healthStatus?.services?.face_recognition?.toUpperCase() || 'CHECKING…'}
              </span>
            </div>

            <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
              <span className="text-slate-500 block text-[10px] uppercase font-bold">Drowsiness Engine</span>
              <span className="font-bold text-emerald-600 flex items-center gap-1.5 mt-1">
                <span className="w-2 h-2 rounded-full bg-emerald-500" />
                {healthStatus?.services?.drowsiness_engine?.toUpperCase() || 'READY'}
              </span>
            </div>

            <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
              <span className="text-slate-500 block text-[10px] uppercase font-bold">Camera Stream</span>
              <span className="font-bold text-blue-600 flex items-center gap-1.5 mt-1">
                <span className="w-2 h-2 rounded-full bg-blue-500" />
                BROWSER WEBCAM
              </span>
            </div>
          </div>
        </Card>

        {/* Fleet Notification Settings */}
        <Card
          title="Notification Dispatch Matrix"
          subtitle="Alert triggers dispatched to the fleet operations console"
        >
          <div className="space-y-3">
            <label className="flex items-center justify-between p-3 rounded-lg border border-slate-150 bg-slate-50/50 cursor-pointer">
              <div>
                <span className="text-xs font-bold text-slate-900 block">Level 1 Alerts (Early Warning)</span>
                <span className="text-[11px] text-slate-500">Short audio beep & subtle UI notification</span>
              </div>
              <input
                type="checkbox"
                checked={notifLevel1}
                onChange={(e) => setNotifLevel1(e.target.checked)}
                className="w-4 h-4 text-blue-600 rounded border-slate-300 focus:ring-blue-500"
              />
            </label>

            <label className="flex items-center justify-between p-3 rounded-lg border border-slate-150 bg-slate-50/50 cursor-pointer">
              <div>
                <span className="text-xs font-bold text-slate-900 block">Level 2 Alerts (Significant Fatigue)</span>
                <span className="text-[11px] text-slate-500">Longer double-pulse audio chime & browser vibration</span>
              </div>
              <input
                type="checkbox"
                checked={notifLevel2}
                onChange={(e) => setNotifLevel2(e.target.checked)}
                className="w-4 h-4 text-blue-600 rounded border-slate-300 focus:ring-blue-500"
              />
            </label>

            <label className="flex items-center justify-between p-3 rounded-lg border border-slate-150 bg-slate-50/50 cursor-pointer">
              <div>
                <span className="text-xs font-bold text-slate-900 block">Level 3 Alerts (Critical Hazard)</span>
                <span className="text-[11px] text-slate-500">Emergency alert siren, vibration, incident logging & evidence snapshot</span>
              </div>
              <input
                type="checkbox"
                checked={notifLevel3}
                onChange={(e) => setNotifLevel3(e.target.checked)}
                className="w-4 h-4 text-blue-600 rounded border-slate-300 focus:ring-blue-500"
              />
            </label>
          </div>
        </Card>

        {/* Action Button */}
        <div className="flex justify-end">
          <button
            type="submit"
            className="px-5 py-2.5 rounded-lg text-xs font-semibold bg-blue-600 hover:bg-blue-700 text-white shadow-sm transition-colors"
          >
            Save Configuration Changes
          </button>
        </div>
      </form>
    </div>
  );
}
