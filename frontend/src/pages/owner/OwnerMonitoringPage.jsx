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
  X,
  Smartphone,
  ShieldAlert,
  CheckCircle2,
} from 'lucide-react';
import { monitoringService } from '../../services/monitoringService';
import { incidentService } from '../../services/incidentService';
import { alcoholService } from '../../services/alcoholService';

export default function OwnerMonitoringPage() {
  const [activeSessions, setActiveSessions] = useState([]);
  const [liveMetrics, setLiveMetrics] = useState({});
  const [loading, setLoading] = useState(true);
  const [selectedEvidence, setSelectedEvidence] = useState(null);
  const [alcoholStatus, setAlcoholStatus] = useState(null);
  const [showResolveModal, setShowResolveModal] = useState(false);
  const [resolveReason, setResolveReason] = useState('');
  const [resolving, setResolving] = useState(false);
  const [resolveError, setResolveError] = useState(null);

  const fetchLiveTelemetry = async () => {
    try {
      const [sessions, metrics, alcStatus] = await Promise.all([
        monitoringService.getActiveSessions(),
        monitoringService.getAllLiveMetrics(),
        alcoholService.getAlcoholStatus().catch(() => null),
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
      if (alcStatus) {
        setAlcoholStatus(alcStatus);
      }
    } catch (err) {
      console.error('Failed to fetch live monitoring telemetry:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleResolveLockout = async (e) => {
    e.preventDefault();
    if (!resolveReason || resolveReason.trim().length < 3) {
      setResolveError('A substantive reason (at least 3 characters) is required to clear a safety lockout.');
      return;
    }

    setResolving(true);
    setResolveError(null);
    try {
      await alcoholService.resolveLockout(resolveReason.trim(), alcoholStatus?.lockout?.incident_id);
      setShowResolveModal(false);
      setResolveReason('');
      await fetchLiveTelemetry();
    } catch (err) {
      console.error('Failed to resolve lockout:', err);
      setResolveError(err.response?.data?.detail || 'Failed to resolve lockout. Ensure you have owner authorization.');
    } finally {
      setResolving(false);
    }
  };

  useEffect(() => {
    fetchLiveTelemetry();
    const interval = setInterval(fetchLiveTelemetry, 1000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="p-6 sm:p-8 max-w-7xl mx-auto space-y-6">
      {/* Active Alcohol Lockout Emergency Banner */}
      {alcoholStatus?.is_locked && (
        <div
          id="owner-alcohol-lockout-banner"
          className="bg-gradient-to-r from-red-950 via-slate-900 to-red-950 border-2 border-red-600 rounded-3xl p-5 sm:p-6 shadow-2xl flex flex-col md:flex-row md:items-center justify-between gap-4 animate-pulse-slow"
        >
          <div className="flex items-center gap-4">
            <div className="p-3.5 bg-red-600/20 text-red-400 rounded-2xl border border-red-500 shadow-lg shadow-red-600/30 shrink-0">
              <ShieldAlert className="w-8 h-8 text-red-400 animate-bounce" />
            </div>
            <div>
              <div className="flex items-center gap-2 mb-1">
                <span className="text-sm sm:text-base font-black text-red-200 uppercase tracking-wide">
                  CRITICAL SAFETY LOCKOUT ACTIVE — MQ-3 ALCOHOL DETECTED
                </span>
                <span className="px-2 py-0.5 bg-red-600 text-white rounded text-[10px] font-bold">
                  HTTP 423
                </span>
              </div>
              <p className="text-xs text-red-300/90 leading-relaxed max-w-3xl">
                Vehicle operation and trip starts are blocked. Sensor Reading: <span className="font-mono font-bold text-red-200">{alcoholStatus.analog ?? alcoholStatus.lockout?.raw_reading ?? '---'} / 1023</span> (Threshold: {alcoholStatus.threshold ?? 200}).
                {alcoholStatus.lockout?.is_acknowledged
                  ? ' Driver has acknowledged the audible alarm.'
                  : ' Driver cab alarm is actively sounding.'}
              </p>
            </div>
          </div>
          <button
            onClick={() => {
              setResolveReason('');
              setResolveError(null);
              setShowResolveModal(true);
            }}
            className="px-5 py-2.5 bg-red-600 hover:bg-red-500 text-white font-extrabold text-xs uppercase tracking-wider rounded-xl shadow-lg shadow-red-600/30 transition active:scale-95 shrink-0"
          >
            Resolve Lockout
          </button>
        </div>
      )}

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
            const isLocked = Boolean(alcoholStatus?.is_locked || session.is_locked || telemetry?.is_locked);
            const isSessionPaused = isLocked || session.status === 'PAUSED' || telemetry?.is_paused || telemetry?.status === 'PAUSED';

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
              kss_label: isLocked ? 'Operation Restricted' : isSessionPaused ? 'Trip Paused' : 'Attentive',
              is_critical: false,
            };
            const alert = (isSessionPaused || isLocked) ? null : telemetry?.latest_alert;

            const isCrit = !isSessionPaused && !isLocked && (fusion.is_critical || alert?.tier === 'critical' || m.microsleep_active);
            const isDistraction = !isSessionPaused && !isLocked && !isCrit && (m.distraction_confirmed || alert?.event_type === 'distraction');
            const isWarn = !isSessionPaused && !isLocked && !isCrit && !isDistraction && (fusion.kss_now >= 6.0 || alert?.tier === 'warning' || m.yawn_active);

            let cardBorder = 'border-slate-800 hover:border-slate-700';
            if (isLocked) cardBorder = 'border-rose-600/80 bg-slate-900/90 shadow-2xl shadow-rose-600/10';
            else if (isSessionPaused) cardBorder = 'border-amber-500/40 bg-slate-900/90 shadow-lg shadow-amber-500/5';
            else if (isCrit) cardBorder = 'border-rose-500/80 shadow-2xl shadow-rose-500/10 animate-pulse';
            else if (isDistraction) cardBorder = 'border-purple-500/80 shadow-2xl shadow-purple-500/10 animate-pulse';
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

                  {isLocked ? (
                    <span className="px-3 py-1 bg-rose-500/15 border border-rose-500/40 text-rose-300 text-xs font-bold rounded-full flex items-center gap-1.5 animate-pulse">
                      <ShieldAlert className="w-3.5 h-3.5 text-rose-400" />
                      LOCKED / OPERATION RESTRICTED
                    </span>
                  ) : isSessionPaused ? (
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
                {alert && !isSessionPaused && !isLocked && (
                  <div className={`p-4 rounded-2xl border mb-5 flex items-center justify-between ${
                    alert.event_type === 'distraction'
                      ? 'bg-purple-500/20 border-purple-500/40 text-purple-300'
                      : alert.tier === 'critical'
                      ? 'bg-rose-500/20 border-rose-500/40 text-rose-300'
                      : 'bg-amber-500/20 border-amber-500/40 text-amber-300'
                  }`}>
                    <div className="flex items-center gap-2 text-xs font-bold">
                      {alert.event_type === 'distraction' ? (
                        <Smartphone className="w-4 h-4 text-purple-400 animate-bounce" />
                      ) : alert.tier === 'critical' ? (
                        <Flame className="w-4 h-4 text-rose-400" />
                      ) : (
                        <AlertTriangle className="w-4 h-4 text-amber-400" />
                      )}
                      <span>{alert.message}</span>
                    </div>

                    {alert.incident_id && (
                      <button
                        onClick={() => setSelectedEvidence({ incident_id: alert.incident_id, event_type: alert.event_type || alert.tier })}
                        className="px-3 py-1.5 bg-slate-950/80 hover:bg-slate-950 text-white text-[11px] font-extrabold rounded-lg border border-white/20 transition flex items-center gap-1 shadow-md"
                      >
                        <Camera className="w-3 h-3 text-cyan-400" /> View Evidence
                      </button>
                    )}
                  </div>
                )}

                {/* Real-time Telemetry Grid or Paused / Locked Indicator */}
                {isLocked ? (
                  <div className="bg-rose-950/30 border border-rose-500/40 rounded-2xl p-5 mb-5 text-center space-y-2">
                    <div className="flex items-center justify-center gap-2 text-rose-400 font-bold text-xs uppercase tracking-wider">
                      <ShieldAlert className="w-4 h-4 text-rose-400" /> Vehicle Operation Restricted
                    </div>
                    <p className="text-xs text-rose-200/90 max-w-md mx-auto">
                      Active MQ-3 alcohol lockout in effect (Sensor Reading:{' '}
                      <span className="font-mono font-bold text-rose-300">
                        {alcoholStatus?.analog ?? '---'}
                      </span>{' '}
                      / 1023, Threshold: {alcoholStatus?.threshold ?? 200}).
                      Trip operation and resumes are locked pending authorized owner clearance.
                    </p>
                  </div>
                ) : isSessionPaused ? (
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
                      {isLocked ? 'Operation Restricted' : isSessionPaused ? 'Trip Paused' : `KSS ${fusion.kss_now.toFixed(1)} / 9.0`}
                    </span>{' '}
                    <span className="text-slate-400">
                      {isLocked ? '(Lockout Active)' : `(${fusion.kss_label})`}
                    </span>
                  </div>
                  <span className={`px-2.5 py-0.5 rounded-md font-bold uppercase text-[10px] ${
                    isLocked
                      ? 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
                      : isSessionPaused
                      ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                      : isCrit
                      ? 'bg-rose-500/20 text-rose-400'
                      : isDistraction
                      ? 'bg-purple-500/20 text-purple-300 border border-purple-500/30'
                      : isWarn
                      ? 'bg-amber-500/20 text-amber-400'
                      : 'bg-emerald-500/20 text-emerald-400'
                  }`}>
                    {isLocked
                      ? 'LOCKED / OPERATION RESTRICTED'
                      : isSessionPaused
                      ? 'Paused / Standby'
                      : isCrit
                      ? 'Critical Alert'
                      : isDistraction
                      ? 'Phone Distraction'
                      : isWarn
                      ? 'Warning'
                      : 'Driver Safe'}
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

      {/* Resolve Alcohol Lockout Modal */}
      {showResolveModal && (
        <div className="fixed inset-0 bg-black/85 backdrop-blur-md z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-3xl max-w-lg w-full overflow-hidden shadow-2xl p-6 space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <div className="flex items-center gap-2 text-rose-400 font-bold text-base">
                <ShieldAlert className="w-5 h-5 text-rose-500" />
                <span>Resolve Alcohol Lockout</span>
              </div>
              <button
                onClick={() => setShowResolveModal(false)}
                className="p-1.5 text-slate-400 hover:text-white rounded-lg bg-slate-800 hover:bg-slate-700 transition"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <p className="text-xs text-slate-400 leading-relaxed">
              Clearing this safety lockout will immediately unlock vehicle ignition and restore trip start/resume capabilities.
              An authorized audit record containing your account ID and resolution rationale will be committed to the safety log.
            </p>

            <form onSubmit={handleResolveLockout} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                  Substantive Audit Reason (Required)
                </label>
                <textarea
                  rows={3}
                  value={resolveReason}
                  onChange={(e) => setResolveReason(e.target.value)}
                  placeholder="e.g. In-person breathalyzer zero test confirmed; sensor baseline recalibrated by technician."
                  className="w-full bg-slate-950 border border-slate-800 rounded-xl p-3 text-xs text-white placeholder-slate-600 focus:outline-none focus:border-cyan-500 resize-none font-sans"
                />
              </div>

              {resolveError && (
                <p className="text-xs text-rose-400 bg-rose-500/10 border border-rose-500/30 p-2.5 rounded-xl">
                  {resolveError}
                </p>
              )}

              <div className="flex items-center justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowResolveModal(false)}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl text-xs font-semibold transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={resolving || resolveReason.trim().length < 3}
                  className="px-5 py-2 bg-rose-600 hover:bg-rose-500 disabled:opacity-50 text-white rounded-xl text-xs font-bold uppercase tracking-wider transition active:scale-95 shadow-lg shadow-rose-600/30"
                >
                  {resolving ? 'Submitting...' : 'Authorize Clearance'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
