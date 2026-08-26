import React, { useState, useEffect } from 'react';
import {
  Activity,
  User,
  Truck,
  ShieldCheck,
  AlertTriangle,
  Flame,
  Camera,
  RefreshCw,
  Clock,
  Eye,
  Smile,
  Compass,
  Pause,
  X,
} from 'lucide-react';
import { monitoringService } from '../../services/monitoringService';
import { incidentService } from '../../services/incidentService';

export default function OwnerMonitoringPage() {
  const [activeSessions, setActiveSessions] = useState([]);
  const [liveMetrics, setLiveMetrics] = useState({});
  const [loading, setLoading] = useState(true);
  const [selectedEvidence, setSelectedEvidence] = useState(null);

  const fetchLiveTelemetry = async () => {
    try {
      const [sessions, metrics] = await Promise.all([
        monitoringService.getActiveSessions(),
        monitoringService.getAllLiveMetrics(),
      ]);
      const validSessions = sessions || [];
      const validIds = new Set(validSessions.map((s) => s.session_id));

      const filteredMetrics = {};
      if (metrics) {
        Object.entries(metrics).forEach(([sid, data]) => {
          if (validIds.has(Number(sid))) {
            filteredMetrics[sid] = data;
          }
        });
      }

      setActiveSessions(validSessions);
      setLiveMetrics(filteredMetrics);
    } catch (err) {
      console.error('Failed to fetch live monitoring telemetry:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLiveTelemetry();
    const interval = setInterval(fetchLiveTelemetry, 1000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="p-6 sm:p-8 max-w-7xl mx-auto space-y-6">
      {/* Top Banner / Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-slate-900 border border-slate-800 p-5 rounded-3xl">
        <div className="flex items-center gap-3">
          <div className="p-3 bg-cyan-500/10 text-cyan-400 rounded-2xl border border-cyan-500/20">
            <Activity className="w-6 h-6 animate-pulse" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-white flex items-center gap-2">
              <span>Live Commercial Surveillance</span>
              <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
                {activeSessions.length} Monitored
              </span>
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Multi-camera multi-modal computer vision telemetry streams & active hazard triggers.
            </p>
          </div>
        </div>

        <button
          onClick={fetchLiveTelemetry}
          className="flex items-center gap-2 px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold rounded-xl border border-slate-700 transition"
        >
          <RefreshCw className="w-3.5 h-3.5" /> Sync Now
        </button>
      </div>

      {/* Main Grid */}
      {loading ? (
        <div className="py-20 text-center text-slate-500 text-sm">
          <div className="w-8 h-8 border-2 border-cyan-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
          Connecting to Active Driver Sessions...
        </div>
      ) : activeSessions.length === 0 ? (
        <div className="py-16 text-center bg-slate-900/50 border border-slate-800 rounded-3xl p-8 max-w-2xl mx-auto">
          <div className="p-4 bg-cyan-500/10 text-cyan-400 rounded-2xl w-fit mx-auto mb-4 border border-cyan-500/20">
            <Truck className="w-8 h-8" />
          </div>
          <h3 className="text-xl font-bold text-white mb-2">No Active Trips in Progress</h3>
          <p className="text-sm text-slate-400 mb-6">
            There are currently no active driver monitoring sessions running. When a driver authenticates on the Driver Cab Portal and starts a shift, live telemetry and alerts will surface here in real time.
          </p>
          <div className="text-xs font-mono text-slate-500 bg-slate-950 p-3 rounded-xl border border-slate-800/80">
            Awaiting WebSocket connections on /ws/monitor/{'{session_id}'}
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {activeSessions.map((session) => {
            const telemetry = liveMetrics[session.session_id];
            const isSessionPaused = session.status === 'PAUSED' || telemetry?.is_paused || telemetry?.status === 'PAUSED';

            const m = telemetry?.metrics || {
              ear: 0.30,
              mar: 0.25,
              perclos: 0.0,
              head_pitch: 0.0,
              head_yaw: 0.0,
              head_roll: 0.0,
              microsleep_active: false,
              yawn_active: false,
            };
            const fusion = telemetry?.fusion || {
              kss_now: 1.0,
              kss_label: isSessionPaused ? 'Trip Paused' : 'Attentive',
              is_critical: false,
            };
            const alert = isSessionPaused ? null : telemetry?.latest_alert;

            const isCrit = !isSessionPaused && (fusion.is_critical || alert?.tier === 'critical' || m.microsleep_active);
            const isWarn = !isSessionPaused && (fusion.kss_now >= 6.0 || alert?.tier === 'warning' || m.yawn_active);

            let cardBorder = 'border-slate-800 hover:border-slate-700';
            if (isSessionPaused) cardBorder = 'border-amber-500/40 bg-slate-900/90 shadow-lg shadow-amber-500/5';
            else if (isCrit) cardBorder = 'border-rose-500/80 shadow-2xl shadow-rose-500/10 animate-pulse';
            else if (isWarn) cardBorder = 'border-amber-500/60 shadow-xl shadow-amber-500/10';

            return (
              <div
                key={session.session_id}
                className={`bg-slate-900 border rounded-3xl p-6 transition-all duration-300 ${cardBorder}`}
              >
                {/* Header */}
                <div className="flex items-start justify-between mb-5">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-2xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-cyan-400 font-bold">
                      #{session.driver_id}
                    </div>
                    <div>
                      <h3 className="text-lg font-bold text-white flex items-center gap-2">
                        <span>{telemetry?.driver_name || `Driver #${session.driver_id}`}</span>
                      </h3>
                      <div className="text-xs text-slate-400 flex items-center gap-2">
                        <Truck className="w-3.5 h-3.5 text-slate-500" />
                        <span className="font-mono text-slate-300 font-semibold">
                          {telemetry?.vehicle_registration || `Vehicle #${session.vehicle_id || 'N/A'}`}
                        </span>
                      </div>
                    </div>
                  </div>

                  {isSessionPaused ? (
                    <span className="px-3 py-1 bg-amber-500/15 border border-amber-500/35 text-amber-300 text-xs font-bold rounded-full flex items-center gap-1.5">
                      <Pause className="w-3 h-3 fill-current text-amber-400" />
                      TRIP PAUSED
                    </span>
                  ) : (
                    <span className="px-3 py-1 bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs font-bold rounded-full flex items-center gap-1.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping"></span>
                      RUNNING TRIP
                    </span>
                  )}
                </div>

                {/* Instant Alert Banner if active */}
                {alert && !isSessionPaused && (
                  <div className={`p-4 rounded-2xl border mb-5 flex items-center justify-between ${
                    alert.tier === 'critical'
                      ? 'bg-rose-500/20 border-rose-500/40 text-rose-300'
                      : 'bg-amber-500/20 border-amber-500/40 text-amber-300'
                  }`}>
                    <div className="flex items-center gap-2 text-xs font-bold">
                      {alert.tier === 'critical' ? <Flame className="w-4 h-4 text-rose-400" /> : <AlertTriangle className="w-4 h-4 text-amber-400" />}
                      <span>{alert.message}</span>
                    </div>

                    {alert.incident_id && (
                      <button
                        onClick={() => setSelectedEvidence({ incident_id: alert.incident_id, event_type: alert.tier })}
                        className="px-3 py-1.5 bg-slate-950/80 hover:bg-slate-950 text-white text-[11px] font-extrabold rounded-lg border border-white/20 transition flex items-center gap-1 shadow-md"
                      >
                        <Camera className="w-3 h-3 text-cyan-400" /> View Evidence
                      </button>
                    )}
                  </div>
                )}

                {/* Real-time Telemetry Grid or Paused Indicator */}
                {isSessionPaused ? (
                  <div className="bg-slate-950/80 border border-amber-500/30 rounded-2xl p-5 mb-5 text-center space-y-1.5">
                    <div className="flex items-center justify-center gap-2 text-amber-400 font-bold text-xs uppercase tracking-wider">
                      <Pause className="w-4 h-4" /> Trip Currently Paused
                    </div>
                    <p className="text-xs text-slate-400">
                      Vehicle is resting or parked. Real-time vision analytics & alert generation are suspended.
                    </p>
                  </div>
                ) : (
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 bg-slate-950/80 border border-slate-800/80 rounded-2xl p-4 mb-5 text-center font-mono">
                    <div>
                      <span className="text-[10px] text-slate-500 uppercase font-sans font-semibold block">EAR</span>
                      <span className={`text-sm font-bold ${m.ear < 0.21 ? 'text-rose-400' : 'text-emerald-400'}`}>
                        {m.ear.toFixed(3)}
                      </span>
                    </div>
                    <div>
                      <span className="text-[10px] text-slate-500 uppercase font-sans font-semibold block">MAR (Yawn)</span>
                      <span className={`text-sm font-bold ${m.mar > 0.55 ? 'text-amber-400' : 'text-slate-200'}`}>
                        {m.mar.toFixed(3)}
                      </span>
                    </div>
                    <div>
                      <span className="text-[10px] text-slate-500 uppercase font-sans font-semibold block">PERCLOS</span>
                      <span className="text-sm font-bold text-blue-400">
                        {(m.perclos * 100).toFixed(1)}%
                      </span>
                    </div>
                    <div>
                      <span className="text-[10px] text-slate-500 uppercase font-sans font-semibold block">Head Pitch</span>
                      <span className={`text-sm font-bold ${m.head_pitch < -15.0 ? 'text-rose-400' : 'text-slate-200'}`}>
                        {m.head_pitch.toFixed(1)}°
                      </span>
                    </div>
                  </div>
                )}

                {/* KSS & Overall Safety status */}
                <div className="flex items-center justify-between border-t border-slate-800/80 pt-4 text-xs">
                  <div>
                    <span className="text-slate-500">Fatigue Level:</span>{' '}
                    <span className="font-bold text-white">
                      {isSessionPaused ? 'Trip Paused' : `KSS ${fusion.kss_now.toFixed(1)} / 9.0`}
                    </span>{' '}
                    <span className="text-slate-400">({fusion.kss_label})</span>
                  </div>
                  <span className={`px-2.5 py-0.5 rounded-md font-bold uppercase text-[10px] ${
                    isSessionPaused
                      ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                      : isCrit
                      ? 'bg-rose-500/20 text-rose-400'
                      : isWarn
                      ? 'bg-amber-500/20 text-amber-400'
                      : 'bg-emerald-500/20 text-emerald-400'
                  }`}>
                    {isSessionPaused ? 'Paused / Standby' : isCrit ? 'Critical Alert' : isWarn ? 'Warning' : 'Driver Safe'}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Evidence Viewer Modal */}
      {selectedEvidence && (
        <div className="fixed inset-0 bg-black/85 backdrop-blur-md z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-3xl max-w-4xl w-full overflow-hidden shadow-2xl animate-in zoom-in-95 duration-200">
            <div className="flex items-center justify-between p-5 border-b border-slate-800">
              <h3 className="text-lg font-bold text-white flex items-center gap-2">
                <span>Incident Evidence Snapshot #{selectedEvidence.incident_id}</span>
                <span className="px-2.5 py-0.5 rounded-full text-xs font-bold uppercase bg-rose-500/10 text-rose-400 border border-rose-500/20">
                  {selectedEvidence.event_type}
                </span>
              </h3>
              <button
                onClick={() => setSelectedEvidence(null)}
                className="p-2 text-slate-400 hover:text-white rounded-xl bg-slate-800 hover:bg-slate-700 transition"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-6 bg-slate-950 flex flex-col items-center justify-center">
              <img
                src={incidentService.getEvidenceUrl(selectedEvidence.incident_id)}
                alt="Drowsiness Evidence"
                className="max-h-[60vh] w-auto rounded-2xl border border-slate-800 shadow-2xl object-contain"
              />
            </div>

            <div className="p-4 border-t border-slate-800 flex justify-end bg-slate-900">
              <button
                onClick={() => setSelectedEvidence(null)}
                className="px-5 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold rounded-xl transition"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
