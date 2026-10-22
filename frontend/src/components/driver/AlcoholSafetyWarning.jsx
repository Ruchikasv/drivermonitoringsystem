import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  ShieldAlert,
  AlertTriangle,
  Volume2,
  VolumeX,
  Phone,
  PhoneOff,
  Clock,
  Activity,
  CheckCircle2,
  Radio,
  Lock,
} from 'lucide-react';
import { alcoholService } from '../../services/alcoholService';
import { soundManager } from '../../utils/soundManager';

/**
 * Driver-Facing MQ-3 Alcohol Safety Warning & Diagnostic Badge.
 *
 * Requirements:
 * 1. While backend reports an active lockout (is_locked: true), displays an unmistakable
 *    full-screen high-contrast red safety warning.
 * 2. Displays: "POTENTIAL ALCOHOL DETECTED — VEHICLE OPERATION RESTRICTED", sensor reading,
 *    event time, and lockout status.
 * 3. Plays a continuous/repeating alarm while event is active and unacknowledged.
 * 4. Silences alarm when driver presses Space or clicks acknowledge (POST /api/alcohol/acknowledge).
 * 5. Space silences audio ONLY. Warning and lockout remain until authorized owner resolution.
 * 6. Restores warning and correct acknowledgement state after page refresh/reconnect (no duplicate loops).
 * 7. Call Owner action using configured owner contact details (never invents fake numbers).
 * 8. Audio channel is independent from drowsiness and distraction alerts.
 * 9. Shows clear diagnostic sensor status badge when warming up, calibrating, disconnected, or normal.
 */
export default function AlcoholSafetyWarning({ sessionId = null, showBadge = true, onStatusChange = null }) {
  const [alcoholData, setAlcoholData] = useState(null);
  const [isAcknowledging, setIsAcknowledging] = useState(false);
  const [acknowledgeError, setAcknowledgeError] = useState(null);
  const isLockedRef = useRef(false);
  const isAcknowledgedRef = useRef(false);

  // Synchronize ref states to avoid stale closures in event listeners
  useEffect(() => {
    isLockedRef.current = Boolean(alcoholData?.is_locked);
    isAcknowledgedRef.current = Boolean(alcoholData?.lockout?.is_acknowledged);
  }, [alcoholData]);

  // Audio lifecycle synchronization with backend state
  const syncAudioAlarm = useCallback((data) => {
    if (!data) return;
    const isLocked = Boolean(data.is_locked);
    const isAcked = Boolean(data.lockout?.is_acknowledged);

    if (isLocked && !isAcked) {
      if (!soundManager.isAlcoholAlarmPlaying) {
        soundManager.startAlcoholAlarm();
      }
    } else {
      if (soundManager.isAlcoholAlarmPlaying) {
        soundManager.stopAlcoholAlarm();
      }
    }
  }, []);

  // Poll status from backend
  const fetchStatus = useCallback(async () => {
    try {
      const data = await alcoholService.getAlcoholStatus(sessionId);
      setAlcoholData(data);
      syncAudioAlarm(data);
      if (onStatusChange) {
        onStatusChange(data);
      }
    } catch (err) {
      console.warn('[AlcoholSafetyWarning] Telemetry poll error:', err);
    }
  }, [sessionId, syncAudioAlarm, onStatusChange]);

  // Handle driver acknowledgement (Silences audio only; lockout remains active)
  const handleAcknowledge = useCallback(async () => {
    if (isAcknowledging) return;
    setIsAcknowledging(true);
    setAcknowledgeError(null);

    // Immediately stop local audio alarm for immediate tactile response
    soundManager.stopAlcoholAlarm();

    try {
      await alcoholService.acknowledgeAlarm(sessionId);
      // Optimistically update local state so UI immediately shows silenced state
      setAlcoholData((prev) => {
        if (!prev) return prev;
        const updatedLockout = prev.lockout
          ? { ...prev.lockout, is_acknowledged: true, acknowledged_at: new Date().toISOString() }
          : { is_locked: true, is_acknowledged: true, acknowledged_at: new Date().toISOString() };
        return {
          ...prev,
          lockout: updatedLockout,
        };
      });
      // Re-fetch to ensure sync with backend DB
      fetchStatus();
    } catch (err) {
      console.error('[AlcoholSafetyWarning] Acknowledgement failed:', err);
      setAcknowledgeError(err.response?.data?.detail || 'Failed to acknowledge alarm. Please retry.');
      // If failed, audio should resume if still locked
      if (isLockedRef.current && !isAcknowledgedRef.current) {
        soundManager.startAlcoholAlarm();
      }
    } finally {
      setIsAcknowledging(false);
    }
  }, [sessionId, isAcknowledging, fetchStatus]);

  // Global Spacebar listener: silences audio only
  useEffect(() => {
    const handleKeyDown = (e) => {
      // Space key triggers alarm silence only if an active unacknowledged lockout exists
      if (e.code === 'Space' || e.key === ' ') {
        if (isLockedRef.current && !isAcknowledgedRef.current) {
          e.preventDefault();
          handleAcknowledge();
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [handleAcknowledge]);

  // Periodic polling interval
  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 1500);

    return () => {
      clearInterval(interval);
      soundManager.stopAlcoholAlarm();
    };
  }, [fetchStatus]);

  const isLocked = Boolean(alcoholData?.is_locked);
  const lockout = alcoholData?.lockout;
  const isAcknowledged = Boolean(lockout?.is_acknowledged);
  const ownerContact = alcoholData?.owner_contact;

  // Format timestamp safely
  const formatTime = (isoString) => {
    if (!isoString) return 'Just now';
    try {
      const d = new Date(isoString);
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) + ' ' + d.toLocaleDateString();
    } catch {
      return isoString;
    }
  };

  // -------------------------------------------------------------------------
  // 1. FULL-SCREEN RED SAFETY WARNING OVERLAY (When Lockout is Active)
  // -------------------------------------------------------------------------
  if (isLocked) {
    return (
      <div
        id="mq3-alcohol-safety-modal"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="alcohol-modal-title"
        className="fixed inset-0 z-[9999] flex flex-col justify-between p-4 sm:p-8 md:p-12 bg-gradient-to-b from-red-950 via-slate-950 to-red-950/95 text-white select-none overflow-y-auto backdrop-blur-xl border-8 border-red-600 animate-pulse-slow"
      >
        {/* Top Emergency Strobe Header */}
        <div className="max-w-4xl mx-auto w-full flex flex-col items-center text-center">
          <div className="flex items-center gap-2 px-4 py-1.5 bg-red-600/30 border border-red-500 rounded-full text-red-200 text-xs font-black tracking-widest uppercase mb-4 shadow-lg shadow-red-600/30">
            <span className="w-2.5 h-2.5 rounded-full bg-red-500 animate-ping" />
            CRITICAL SAFETY LOCKOUT &bull; EURO NCAP PROTOCOL
          </div>

          <div className="relative mb-4">
            <div className="w-24 h-24 sm:w-28 sm:h-28 rounded-3xl bg-red-600/20 border-2 border-red-500 flex items-center justify-center text-red-500 shadow-2xl shadow-red-600/50">
              <ShieldAlert className="w-14 h-14 sm:w-16 sm:h-16 animate-bounce" />
            </div>
            <span className="absolute -top-2 -right-2 p-2 bg-red-600 text-white rounded-full shadow-lg">
              <Lock className="w-5 h-5" />
            </span>
          </div>

          <h1
            id="alcohol-modal-title"
            className="text-2xl sm:text-4xl md:text-5xl font-black tracking-tight text-red-100 uppercase mb-3 drop-shadow-md"
          >
            POTENTIAL ALCOHOL DETECTED — VEHICLE OPERATION RESTRICTED
          </h1>

          <p className="text-sm sm:text-base text-red-200/90 max-w-2xl font-medium leading-relaxed">
            Safety interlock has engaged. Engine ignition, trip start, and vehicle resumption are strictly restricted
            in compliance with commercial transport safety regulations.
          </p>
        </div>

        {/* Center Information Cards */}
        <div className="max-w-4xl mx-auto w-full my-6 grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Card 1: Sensor & Event Telemetry */}
          <div className="bg-slate-900/90 border-2 border-red-600/50 rounded-2xl p-5 shadow-xl flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between text-xs font-bold text-red-400 uppercase tracking-wider pb-3 border-b border-red-900/50 mb-4">
                <span className="flex items-center gap-1.5">
                  <Activity className="w-4 h-4 text-red-400" /> Sensor Telemetry
                </span>
                <span className="font-mono bg-red-950 px-2 py-0.5 rounded border border-red-800 text-red-300">
                  {lockout?.event_id || 'ALC-EVENT'}
                </span>
              </div>

              <div className="space-y-3">
                <div className="flex justify-between items-center">
                  <span className="text-xs text-slate-400">Raw Sensor Reading:</span>
                  <span className="text-lg font-black font-mono text-red-300">
                    {alcoholData?.analog ?? lockout?.raw_reading ?? '---'}{' '}
                    <span className="text-xs font-normal text-slate-500">
                      / 1023 (Threshold: {alcoholData?.threshold ?? lockout?.threshold ?? 200})
                    </span>
                  </span>
                </div>

                <div className="flex justify-between items-center">
                  <span className="text-xs text-slate-400">Baseline Reference:</span>
                  <span className="text-sm font-bold font-mono text-slate-300">
                    {alcoholData?.baseline ?? lockout?.baseline ?? 'Calibrated'}
                  </span>
                </div>

                <div className="flex justify-between items-center">
                  <span className="text-xs text-slate-400">Event Detected At:</span>
                  <span className="text-xs font-bold font-mono text-red-300 flex items-center gap-1">
                    <Clock className="w-3.5 h-3.5 text-red-400" />
                    {formatTime(lockout?.detected_at)}
                  </span>
                </div>

                <div className="flex justify-between items-center pt-2 border-t border-slate-800">
                  <span className="text-xs text-slate-400">Vehicle Lockout Status:</span>
                  <span className="text-xs font-black uppercase text-red-400 bg-red-950/80 px-2.5 py-1 rounded border border-red-800">
                    LOCKED (HTTP 423)
                  </span>
                </div>
              </div>
            </div>

            <div className="mt-4 pt-3 border-t border-slate-800/80 text-[11px] text-slate-400">
              Trip lifecycle controls (start/resume) are locked on the backend. Only an authorized fleet owner can clear this restriction.
            </div>
          </div>

          {/* Card 2: Alarm Acknowledgement & Call Owner */}
          <div className="bg-slate-900/90 border-2 border-red-600/50 rounded-2xl p-5 shadow-xl flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between text-xs font-bold text-red-400 uppercase tracking-wider pb-3 border-b border-red-900/50 mb-4">
                <span className="flex items-center gap-1.5">
                  <Radio className="w-4 h-4 text-red-400" /> Driver Safety Actions
                </span>
                <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                  isAcknowledged
                    ? 'bg-amber-950 text-amber-300 border border-amber-800'
                    : 'bg-red-950 text-red-300 border border-red-700 animate-pulse'
                }`}>
                  {isAcknowledged ? 'AUDIO SILENCED' : 'ALARM SOUNDING'}
                </span>
              </div>

              {/* Alarm Silence Action */}
              <div className="mb-4">
                {!isAcknowledged ? (
                  <button
                    id="silence-alcohol-alarm-btn"
                    onClick={handleAcknowledge}
                    disabled={isAcknowledging}
                    className="w-full flex flex-col items-center justify-center p-3 sm:p-4 bg-gradient-to-r from-red-600 to-rose-700 hover:from-red-500 hover:to-rose-600 active:scale-98 text-white rounded-xl font-black text-sm uppercase tracking-wider shadow-lg shadow-red-600/30 transition border-2 border-red-400"
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <VolumeX className="w-5 h-5 animate-pulse" />
                      <span>{isAcknowledging ? 'Silencing...' : 'SILENCE AUDIBLE ALARM'}</span>
                    </div>
                    <span className="text-[11px] font-mono text-red-200 tracking-normal font-normal">
                      Press [ SPACEBAR ] or Click to silence
                    </span>
                  </button>
                ) : (
                  <div className="p-3 bg-amber-500/10 border border-amber-500/30 rounded-xl text-center">
                    <div className="flex items-center justify-center gap-1.5 text-xs font-bold text-amber-300 mb-0.5">
                      <CheckCircle2 className="w-4 h-4 text-amber-400" />
                      Audio Alarm Silenced by Driver
                    </div>
                    <p className="text-[11px] text-amber-400/80">
                      Vehicle operation remains restricted until fleet owner resolution.
                    </p>
                  </div>
                )}
                {acknowledgeError && (
                  <p className="text-xs text-rose-400 mt-2 text-center">{acknowledgeError}</p>
                )}
              </div>

              {/* Call Owner Action */}
              <div>
                <div className="text-xs text-slate-400 mb-2 font-medium">Fleet Authorization Clearance:</div>
                {ownerContact?.phone_configured && ownerContact?.phone ? (
                  <a
                    id="call-owner-btn"
                    href={`tel:${ownerContact.phone}`}
                    className="w-full flex items-center justify-center gap-2 p-3 bg-slate-800 hover:bg-slate-700 active:scale-98 text-white rounded-xl font-bold text-xs uppercase tracking-wider border border-slate-700 hover:border-cyan-500 transition shadow-md"
                  >
                    <Phone className="w-4 h-4 text-emerald-400" />
                    <span>Call Owner: {ownerContact.name || 'Fleet Manager'} ({ownerContact.phone})</span>
                  </a>
                ) : (
                  <div className="p-3 bg-slate-800/80 border border-slate-700/80 rounded-xl text-xs text-slate-400 flex items-start gap-2.5">
                    <PhoneOff className="w-4 h-4 text-slate-500 mt-0.5 shrink-0" />
                    <div>
                      <div className="font-semibold text-slate-300">Owner Phone Not Configured</div>
                      <div className="text-[11px] text-slate-400 mt-0.5">
                        Owner phone number is not configured in fleet system. Please contact operations dispatch via two-way radio.
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>

            <div className="mt-4 pt-3 border-t border-slate-800/80 text-[11px] text-slate-400">
              Spacebar silences alarm audio only. Safety lockout remains active until authorized owner resolution.
            </div>
          </div>
        </div>

        {/* Footer Regulatory Disclaimer */}
        <div className="max-w-4xl mx-auto w-full pt-4 border-t border-red-900/40 text-center text-[11px] text-red-300/70 font-mono">
          {alcoholData?.disclaimer ||
            'MQ-3 is an alcohol-vapor prototype sensor, not a certified evidentiary breathalyzer. Vehicle lockout is enforced for transport safety compliance.'}
        </div>
      </div>
    );
  }

  // -------------------------------------------------------------------------
  // 2. DIAGNOSTIC BADGE (When NOT Locked: Warmup, Calibrating, Disconnected, or Normal)
  // -------------------------------------------------------------------------
  if (!showBadge || !alcoholData) {
    return null;
  }

  const sensorState = alcoholData.state || (alcoholData.is_connected ? 'NORMAL' : 'SENSOR_DISCONNECTED');
  const analogVal = alcoholData.analog;

  if (sensorState === 'WARMING_UP') {
    return (
      <div
        id="mq3-sensor-badge"
        className="flex items-center gap-1.5 px-2.5 py-1 bg-amber-500/10 border border-amber-500/30 text-amber-300 text-xs font-semibold rounded-lg shadow-sm"
        title="MQ-3 heater coil is pre-heating. Readings are ignored during warmup."
      >
        <span className="w-2 h-2 rounded-full bg-amber-400 animate-ping" />
        <span>MQ-3 Warming Up ({alcoholData.warmup_remaining_seconds || '15'}s)</span>
      </div>
    );
  }

  if (sensorState === 'CALIBRATING') {
    return (
      <div
        id="mq3-sensor-badge"
        className="flex items-center gap-1.5 px-2.5 py-1 bg-sky-500/10 border border-sky-500/30 text-sky-300 text-xs font-semibold rounded-lg shadow-sm"
        title="MQ-3 clean-air baseline calibration in progress."
      >
        <span className="w-2 h-2 rounded-full bg-sky-400 animate-pulse" />
        <span>MQ-3 Calibrating Baseline...</span>
      </div>
    );
  }

  if (sensorState === 'SENSOR_FAULT') {
    return (
      <div
        id="mq3-sensor-badge"
        className="flex items-center gap-1.5 px-2.5 py-1 bg-rose-500/15 border border-rose-500/40 text-rose-300 text-xs font-semibold rounded-lg shadow-sm"
        title="Sensor readings stuck at rails (0 or 1023). Hardware inspection recommended."
      >
        <AlertTriangle className="w-3.5 h-3.5 text-rose-400" />
        <span>MQ-3 Sensor Fault Check</span>
      </div>
    );
  }

  if (sensorState === 'SENSOR_DISCONNECTED' || !alcoholData.is_connected) {
    return (
      <div
        id="mq3-sensor-badge"
        className="flex items-center gap-1.5 px-2.5 py-1 bg-slate-800 border border-slate-700 text-slate-400 text-xs font-semibold rounded-lg shadow-sm"
        title={`MQ-3 serial gateway searching on ${alcoholData.port || 'COM port'}`}
      >
        <span className="w-2 h-2 rounded-full bg-slate-500" />
        <span>MQ-3 Sensor Offline</span>
      </div>
    );
  }

  // Normal Connected State
  return (
    <div
      id="mq3-sensor-badge"
      className="flex items-center gap-1.5 px-2.5 py-1 bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs font-semibold rounded-lg shadow-sm"
      title={`MQ-3 Vapor Sensor Active. Live reading: ${analogVal ?? '---'} (Threshold: ${alcoholData.threshold || 200})`}
    >
      <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
      <span>MQ-3 Alcohol Safe ({analogVal ?? 'Active'})</span>
    </div>
  );
}
