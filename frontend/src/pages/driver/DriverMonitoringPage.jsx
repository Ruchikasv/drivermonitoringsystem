import React, { useState, useEffect, useRef } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import {
  ShieldCheck,
  AlertTriangle,
  Flame,
  Volume2,
  VolumeX,
  StopCircle,
  Pause,
  Play,
  Eye,
  Smile,
  Activity,
  Compass,
  CheckCircle2,
  Clock,
} from 'lucide-react';
import { monitoringService } from '../../services/monitoringService';
import { soundManager } from '../../utils/soundManager';

export default function DriverMonitoringPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const sessionId = searchParams.get('session');
  const driverId = searchParams.get('driver');

  const [connected, setConnected] = useState(false);
  const [frameB64, setFrameB64] = useState(null);
  const [cameraReady, setCameraReady] = useState(false);
  const [cameraError, setCameraError] = useState(null);
  const [driverInfo, setDriverInfo] = useState({ name: 'Driver', vehicle: 'Commercial Vehicle' });
  const [isPaused, setIsPaused] = useState(false);
  const [metrics, setMetrics] = useState({
    ear: 0.30,
    mar: 0.25,
    perclos: 0.0,
    head_pitch: 0.0,
    head_yaw: 0.0,
    head_roll: 0.0,
    face_detected: true,
    microsleep_active: false,
    yawn_active: false,
    head_nod_active: false,
  });
  const [fusion, setFusion] = useState({
    kss_now: 1.0,
    kss_label: 'Extremely alert',
    is_critical: false,
    p_critical_soon: null,
  });
  const [currentAlert, setCurrentAlert] = useState(null);
  const [audioEnabled, setAudioEnabled] = useState(true);
  const [tripSummary, setTripSummary] = useState(null);
  const [showEndModal, setShowEndModal] = useState(false);
  const [ending, setEnding] = useState(false);
  const [pausing, setPausing] = useState(false);

  const wsRef = useRef(null);
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);
  const captureIntervalRef = useRef(null);
  const isSendingRef = useRef(false);
  const startTimeRef = useRef(Date.now());

  const handleAudioToggle = () => {
    const nextState = !audioEnabled;
    setAudioEnabled(nextState);
    soundManager.setEnabled(nextState);
    if (nextState) {
      soundManager.unlockAudio();
    }
  };

  const stopWebcam = () => {
    if (captureIntervalRef.current) {
      clearInterval(captureIntervalRef.current);
      captureIntervalRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => {
        track.stop();
      });
      streamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    setCameraReady(false);
  };

  const startWebcam = async () => {
    stopWebcam();
    setCameraError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' },
        audio: false,
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        videoRef.current.onloadedmetadata = () => {
          videoRef.current.play().catch(() => {});
          setCameraReady(true);
        };
      }
    } catch (err) {
      console.error('Monitoring webcam error:', err);
      setCameraError('Unable to access monitoring webcam. Please ensure camera permissions are granted.');
    }
  };

  useEffect(() => {
    if (!sessionId) {
      navigate('/driver');
      return;
    }

    const checkInitialStatus = async () => {
      try {
        const sess = await monitoringService.getSession(sessionId);
        if (sess) {
          if (sess.status === 'PAUSED') {
            setIsPaused(true);
          } else if (sess.status === 'COMPLETED' || sess.status === 'INTERRUPTED') {
            navigate('/driver');
            return;
          }
        }
      } catch (e) {
        console.error('Error checking session status:', e);
      }
    };
    checkInitialStatus();

    startWebcam();

    const token = searchParams.get('token');
    const wsUrl = monitoringService.getWebSocketUrl(sessionId, token);
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      console.log('Connected to driver monitoring WebSocket:', sessionId);

      // Flow-controlled frame transmission to backend (no queue backlog)
      if (captureIntervalRef.current) clearInterval(captureIntervalRef.current);
      isSendingRef.current = false;
      captureIntervalRef.current = setInterval(() => {
        if (!videoRef.current || ws.readyState !== WebSocket.OPEN) return;
        if (isSendingRef.current || ws.bufferedAmount > 0) return;
        const video = videoRef.current;
        if (video.videoWidth === 0 || video.videoHeight === 0 || video.paused) return;

        if (!canvasRef.current) {
          canvasRef.current = document.createElement('canvas');
        }
        const canvas = canvasRef.current;
        canvas.width = 640;
        canvas.height = 480;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(video, 0, 0, 640, 480);

        const b64 = canvas.toDataURL('image/jpeg', 0.60);
        isSendingRef.current = true;
        ws.send(JSON.stringify({ frame: b64 }));
      }, 85);
    };

    ws.onmessage = (event) => {
      isSendingRef.current = false;
      try {
        const data = JSON.parse(event.data);

        if (data.error) {
          console.error('WebSocket server error:', data.error);
          setCameraError(data.error);
          return;
        }

        if (data.status === 'PAUSED' || data.is_paused === true) {
          setIsPaused(true);
          setCurrentAlert(null);
          soundManager.stop();
        } else if (data.status === 'ACTIVE' || data.is_paused === false) {
          setIsPaused(false);
        }

        if (data.driver_name) {
          setDriverInfo({
            name: data.driver_name,
            vehicle: data.vehicle_registration || 'Commercial Vehicle',
          });
        }

        if (data.frame_b64) {
          setFrameB64(data.frame_b64);
        }

        if (data.metrics) {
          setMetrics(data.metrics);
        }

        if (data.fusion) {
          setFusion(data.fusion);
        }

        const isCriticalActive = Boolean(data.critical_active) && !data.is_paused;

        if (isCriticalActive) {
          soundManager.playAlert("critical");
        } else {
          // If critical is no longer active, ensure critical siren is stopped
          if (soundManager.isCriticalPlaying) {
            soundManager.stopCriticalSiren();
          }

          // Handle one-shot warning / nudge alerts if present
          if (data.alert && !data.is_paused) {
            if (data.alert.tier === "warning") {
              soundManager.playAlert("warning");
            } else if (data.alert.tier === "nudge") {
              soundManager.playAlert("nudge");
            }
          }
        }

        if (data.alert && !data.is_paused) {
          setCurrentAlert(data.alert);
        } else if (!isCriticalActive) {
          setCurrentAlert(null);
        }
      } catch (err) {
        console.error('WebSocket message parsing error:', err);
      }
    };

    ws.onerror = () => {
      isSendingRef.current = false;
    };

    ws.onclose = () => {
      isSendingRef.current = false;
      setConnected(false);
      console.log('WebSocket closed.');
    };

    return () => {
      stopWebcam();
      soundManager.stop();
      if (ws.readyState === WebSocket.OPEN) {
        ws.close();
      }
    };
  }, [sessionId]);

  const handlePauseTrip = async () => {
    setPausing(true);
    try {
      soundManager.stop();
      setCurrentAlert(null);
      await monitoringService.pauseSession(sessionId);
      setIsPaused(true);
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ action: 'pause' }));
      }
    } catch (err) {
      console.error('Error pausing session:', err);
    } finally {
      setPausing(false);
    }
  };

  const handleResumeTrip = async () => {
    setPausing(true);
    try {
      soundManager.unlockAudio();
      soundManager.stop();
      setCurrentAlert(null);
      await monitoringService.resumeSession(sessionId);
      setIsPaused(false);
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ action: 'resume' }));
      }
    } catch (err) {
      console.error('Error resuming session:', err);
    } finally {
      setPausing(false);
    }
  };

  const handleEndTrip = async () => {
    setEnding(true);
    try {
      soundManager.stop();
      stopWebcam();
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.close();
      }
      await monitoringService.endSession(sessionId);

      const elapsedSec = Math.round((Date.now() - startTimeRef.current) / 1000);
      const minutes = Math.floor(elapsedSec / 60);
      const seconds = elapsedSec % 60;

      setTripSummary({
        driverName: driverInfo.name,
        vehicle: driverInfo.vehicle,
        duration: `${minutes}m ${seconds}s`,
        kssFinal: fusion.kss_now,
      });
      setShowEndModal(false);
    } catch (err) {
      console.error('Error ending session:', err);
      navigate('/driver');
    } finally {
      setEnding(false);
    }
  };

  const isCritical = !isPaused && (fusion.is_critical || currentAlert?.tier === 'critical' || metrics.microsleep_active);
  const isWarning = !isPaused && !isCritical && (fusion.kss_now >= 6.0 || currentAlert?.tier === 'warning' || metrics.yawn_active);
  const isNudge = !isPaused && !isCritical && !isWarning && (fusion.kss_now >= 4.5 || currentAlert?.tier === 'nudge' || metrics.perclos >= 0.20);

  let statusBg = 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400';
  let statusTitle = 'SAFE & ATTENTIVE';
  let statusSubtitle = 'No active hazard detected';
  let statusIcon = <ShieldCheck className="w-5 h-5 text-emerald-400" />;

  if (isPaused) {
    statusBg = 'bg-amber-500/20 border-amber-500/50 text-amber-300';
    statusTitle = 'TRIP PAUSED';
    statusSubtitle = 'Drowsiness monitoring & alert sounds suspended';
    statusIcon = <Pause className="w-5 h-5 text-amber-400" />;
  } else if (isCritical) {
    statusBg = 'bg-rose-500/20 border-rose-500/50 text-rose-400 animate-pulse';
    statusTitle = 'LEVEL 3 — CRITICAL DROWSINESS';
    statusSubtitle = 'IMMEDIATE ATTENTION REQUIRED';
    statusIcon = <Flame className="w-5 h-5 text-rose-400 animate-bounce" />;
  } else if (isWarning) {
    statusBg = 'bg-amber-500/15 border-amber-500/40 text-amber-400';
    statusTitle = 'LEVEL 2 — DROWSINESS WARNING';
    statusSubtitle = 'Take immediate corrective action';
    statusIcon = <AlertTriangle className="w-5 h-5 text-amber-400" />;
  } else if (isNudge) {
    statusBg = 'bg-cyan-500/15 border-cyan-500/30 text-cyan-400';
    statusTitle = 'LEVEL 1 — DROWSINESS DETECTED';
    statusSubtitle = 'Please stay alert';
    statusIcon = <AlertTriangle className="w-5 h-5 text-cyan-400" />;
  }


  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col justify-between p-4 sm:p-6 font-sans select-none">
      {/* Top Telemetry Header */}
      <header className="flex items-center justify-between bg-slate-900/80 border border-slate-800/80 rounded-2xl px-5 py-3.5 backdrop-blur">
        <div className="flex items-center gap-3">
          <div className={`w-3 h-3 rounded-full ${
            !connected ? 'bg-rose-500' : isPaused ? 'bg-amber-400 animate-pulse' : 'bg-emerald-400 shadow-lg shadow-emerald-500/50 animate-pulse'
          }`} />
          <div>
            <div className="text-sm font-bold text-white flex items-center gap-2">
              <span>{driverInfo.name}</span>
              <span className="text-xs px-2 py-0.5 bg-slate-800 text-slate-300 rounded-md font-mono">
                {driverInfo.vehicle}
              </span>
              {isPaused && (
                <span className="text-xs px-2.5 py-0.5 bg-amber-500/20 text-amber-300 border border-amber-500/40 rounded-md font-bold uppercase tracking-wider">
                  PAUSED
                </span>
              )}
            </div>
            <div className="text-[11px] text-slate-400">
              Session #{sessionId} &bull; {connected ? (isPaused ? 'Trip Paused (Suspended)' : 'Live Active Stream') : 'Connecting to FYP Engine...'}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Temporary Manual Verification Button for Level 3 Siren */}
          <button
            onClick={() => {
              if (soundManager.isCriticalPlaying) {
                soundManager.stopCriticalSiren();
              } else {
                soundManager.unlockAudio();
                soundManager.playAlert('critical');
              }
            }}
            className="px-3.5 py-2 text-xs font-extrabold rounded-xl border border-rose-500/40 bg-rose-500/15 hover:bg-rose-500/25 text-rose-300 transition active:scale-95 shadow-sm"
            title="Development verification helper: toggles continuous Level 3 critical siren"
          >
            🚨 Test Critical Siren
          </button>

          <button
            onClick={handleAudioToggle}
            className={`p-2.5 rounded-xl border transition ${
              audioEnabled ? 'bg-cyan-500/10 border-cyan-500/30 text-cyan-400' : 'bg-slate-800 border-slate-700 text-slate-500'
            }`}
            title={audioEnabled ? 'Audio Alarms Active' : 'Audio Muted'}
          >
            {audioEnabled ? <Volume2 className="w-5 h-5" /> : <VolumeX className="w-5 h-5" />}
          </button>

          {isPaused ? (
            <button
              disabled={pausing}
              onClick={handleResumeTrip}
              className="flex items-center gap-2 px-5 py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white font-extrabold text-xs uppercase tracking-wider rounded-xl shadow-lg shadow-emerald-600/20 transition active:scale-95"
            >
              <Play className="w-4 h-4 fill-current" /> Resume Trip
            </button>
          ) : (
            <button
              disabled={pausing}
              onClick={handlePauseTrip}
              className="flex items-center gap-2 px-5 py-2.5 bg-amber-600 hover:bg-amber-500 text-white font-extrabold text-xs uppercase tracking-wider rounded-xl shadow-lg shadow-amber-600/20 transition active:scale-95"
            >
              <Pause className="w-4 h-4 fill-current" /> Pause Trip
            </button>
          )}

          <button
            onClick={() => setShowEndModal(true)}
            className="flex items-center gap-2 px-5 py-2.5 bg-rose-600 hover:bg-rose-500 text-white font-extrabold text-xs uppercase tracking-wider rounded-xl shadow-lg shadow-rose-600/20 transition active:scale-95"
          >
            <StopCircle className="w-4 h-4" /> End Trip
          </button>
        </div>
      </header>

      {/* Main Monitoring Hub */}
      <main className="grid grid-cols-1 lg:grid-cols-12 gap-5 my-auto py-4 items-center max-w-7xl mx-auto w-full">
        {/* Left / Center: Camera Viewport */}
        <div className="lg:col-span-8 flex flex-col items-center">
          {/* Status Bar */}
          <div className={`w-full mb-3 px-5 py-3 rounded-2xl border flex items-center justify-between font-bold text-sm tracking-wide ${statusBg}`}>
            <div className="flex items-center gap-2.5">
              {statusIcon}
              <div>
                <div className="text-sm font-extrabold tracking-wide">{statusTitle}</div>
                <div className="text-xs font-normal opacity-90">{statusSubtitle}</div>
              </div>
            </div>
            <div className="text-xs uppercase opacity-80 font-mono text-right">
              <div>KSS Estimate: {fusion.kss_now.toFixed(1)} / 9.0</div>
              <div className="text-[10px] text-slate-400 font-normal">{fusion.kss_label}</div>
            </div>
          </div>

          {/* Camera Frame Container */}
          <div className="relative w-full aspect-[4/3] bg-slate-900 rounded-3xl overflow-hidden border border-slate-800 shadow-2xl flex items-center justify-center">
            {/* Real-time Hardware-Accelerated Local Camera Video Feed */}
            <video
              ref={videoRef}
              playsInline
              autoPlay
              muted
              className={`w-full h-full object-cover transform -scale-x-100 ${cameraReady ? 'block' : 'hidden'}`}
            />

            {cameraError ? (
              <div className="flex flex-col items-center text-rose-400 text-sm gap-3 p-6 text-center">
                <AlertTriangle className="w-10 h-10 text-rose-500" />
                <span className="font-semibold">{cameraError}</span>
                <button
                  onClick={startWebcam}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white rounded-xl text-xs font-bold border border-slate-700 transition"
                >
                  Retry Camera Access
                </button>
              </div>
            ) : !cameraReady ? (
              <div className="flex flex-col items-center text-slate-500 text-sm gap-3">
                <div className="w-10 h-10 border-2 border-cyan-500 border-t-transparent rounded-full animate-spin" />
                <span>Initializing Real-Time Webcam Stream...</span>
              </div>
            ) : null}

            {/* Active Condition Badges & Face Detection Notice */}
            <div className="absolute top-4 left-4 flex flex-col gap-2 pointer-events-none">
              {metrics.face_detected === false && (
                <span className="px-3 py-1 bg-amber-500 text-slate-950 font-bold text-xs rounded-lg shadow-lg flex items-center gap-1.5">
                  <AlertTriangle className="w-3.5 h-3.5" /> FACE NOT DETECTED
                </span>
              )}
              {metrics.microsleep_active && (
                <span className="px-3 py-1 bg-rose-500 text-white font-bold text-xs rounded-lg shadow-lg animate-pulse flex items-center gap-1.5">
                  <Eye className="w-3.5 h-3.5" /> MICROSLEEP DETECTED
                </span>
              )}
              {metrics.yawn_active && (
                <span className="px-3 py-1 bg-amber-500 text-slate-950 font-bold text-xs rounded-lg shadow-lg animate-pulse flex items-center gap-1.5">
                  <Smile className="w-3.5 h-3.5" /> YAWN DETECTED
                </span>
              )}
              {metrics.head_nod_active && (
                <span className="px-3 py-1 bg-rose-500 text-white font-bold text-xs rounded-lg shadow-lg animate-pulse flex items-center gap-1.5">
                  <Compass className="w-3.5 h-3.5" /> HEAD NODDING FORWARD
                </span>
              )}
            </div>

            {/* Paused Overlay */}
            {isPaused && (
              <div className="absolute inset-0 bg-slate-950/60 backdrop-blur-sm flex flex-col items-center justify-center p-6 text-center z-10">
                <div className="p-4 bg-amber-500/20 text-amber-400 rounded-3xl border border-amber-500/40 shadow-xl mb-3 animate-pulse">
                  <Pause className="w-10 h-10" />
                </div>
                <h4 className="text-xl font-extrabold text-white tracking-wide">TRIP PAUSED</h4>
                <p className="text-xs text-slate-300 max-w-xs mt-1 mb-4">
                  Drowsiness detection & audio alerts are suspended while parked or resting.
                </p>
                <button
                  disabled={pausing}
                  onClick={handleResumeTrip}
                  className="flex items-center gap-2 px-6 py-2.5 bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold rounded-xl shadow-lg transition active:scale-95 text-xs uppercase tracking-wider"
                >
                  <Play className="w-4 h-4 fill-current" /> Resume Trip
                </button>
              </div>
            )}

            {/* Subtle Camera HUD Corner markings */}
            <div className="absolute top-3 right-3 text-[10px] font-mono text-cyan-400/80 bg-slate-950/70 px-2 py-1 rounded-md border border-cyan-500/20 pointer-events-none">
              {isPaused ? 'MONITORING SUSPENDED' : 'FACIAL MESH • 478 PTS'}
            </div>
          </div>
        </div>

        {/* Right Column: Real-time Telemetry Gauges */}
        <div className="lg:col-span-4 bg-slate-900/90 border border-slate-800 rounded-3xl p-5 space-y-4">
          <h3 className="text-sm font-bold uppercase tracking-wider text-slate-400 flex items-center gap-2">
            <Activity className="w-4 h-4 text-cyan-400" /> Real-Time Driver Telemetry
          </h3>

          {/* Contributing Factors Notification */}
          {metrics.contributing_factors && metrics.contributing_factors.length > 0 && (
            <div className="bg-amber-500/10 border border-amber-500/30 rounded-2xl p-3 text-xs space-y-1">
              <span className="text-[11px] font-bold text-amber-400 uppercase block">Active Fatigue Signals:</span>
              <div className="flex flex-wrap gap-1.5">
                {metrics.contributing_factors.map((factor, idx) => (
                  <span key={idx} className="px-2 py-0.5 bg-amber-500/20 text-amber-300 rounded text-[11px] font-semibold">
                    {factor}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Metric 1: Eye Aspect Ratio (EAR) */}
          <div className="bg-slate-950 border border-slate-800/80 rounded-2xl p-3.5">
            <div className="flex justify-between text-xs mb-1.5">
              <span className="text-slate-400 font-semibold flex items-center gap-1.5">
                <Eye className="w-3.5 h-3.5 text-cyan-400" /> Eye Aspect Ratio (EAR)
              </span>
              <span className={`font-mono font-bold ${metrics.ear < 0.21 ? 'text-rose-400' : 'text-emerald-400'}`}>
                {metrics.ear.toFixed(3)}
              </span>
            </div>
            <div className="w-full h-2 bg-slate-800 rounded-full overflow-hidden">
              <div
                className={`h-full transition-all duration-100 ${metrics.ear < 0.21 ? 'bg-rose-500' : 'bg-cyan-500'}`}
                style={{ width: `${Math.min(100, (metrics.ear / 0.40) * 100)}%` }}
              />
            </div>
            <div className="flex justify-between text-[10px] text-slate-500 mt-1">
              <span>Threshold: 0.21 (Closed)</span>
              <span>Open: &gt;0.25</span>
            </div>
          </div>

          {/* Metric 2: Mouth Aspect Ratio (MAR) */}
          <div className="bg-slate-950 border border-slate-800/80 rounded-2xl p-3.5">
            <div className="flex justify-between text-xs mb-1.5">
              <span className="text-slate-400 font-semibold flex items-center gap-1.5">
                <Smile className="w-3.5 h-3.5 text-amber-400" /> Mouth Aspect Ratio (MAR)
              </span>
              <span className={`font-mono font-bold ${metrics.mar > 0.55 ? 'text-amber-400' : 'text-slate-200'}`}>
                {metrics.mar.toFixed(3)}
              </span>
            </div>
            <div className="w-full h-2 bg-slate-800 rounded-full overflow-hidden">
              <div
                className={`h-full transition-all duration-100 ${metrics.mar > 0.55 ? 'bg-amber-500' : 'bg-slate-500'}`}
                style={{ width: `${Math.min(100, (metrics.mar / 1.0) * 100)}%` }}
              />
            </div>
            <div className="flex justify-between text-[10px] text-slate-500 mt-1">
              <span>Threshold: 0.55 (Yawn)</span>
              <span>Normal: &lt;0.40</span>
            </div>
          </div>

          {/* Metric 3: PERCLOS Rolling 60s */}
          <div className="bg-slate-950 border border-slate-800/80 rounded-2xl p-3.5">
            <div className="flex justify-between text-xs mb-1.5">
              <span className="text-slate-400 font-semibold flex items-center gap-1.5">
                <Clock className="w-3.5 h-3.5 text-blue-400" /> PERCLOS (60s Window)
              </span>
              <span className={`font-mono font-bold ${metrics.perclos > 0.15 ? 'text-rose-400' : 'text-cyan-400'}`}>
                {(metrics.perclos * 100).toFixed(1)}%
              </span>
            </div>
            <div className="w-full h-2 bg-slate-800 rounded-full overflow-hidden">
              <div
                className={`h-full transition-all duration-100 ${metrics.perclos > 0.15 ? 'bg-rose-500' : 'bg-blue-500'}`}
                style={{ width: `${Math.min(100, metrics.perclos * 100 * 2.5)}%` }}
              />
            </div>
          </div>

          {/* Metric 4: Head Pose Pitch / Nodding */}
          <div className="bg-slate-950 border border-slate-800/80 rounded-2xl p-3.5 grid grid-cols-3 gap-2 text-center text-xs">
            <div>
              <span className="text-slate-500 block text-[10px]">Pitch</span>
              <span className={`font-mono font-bold ${metrics.head_pitch < -15.0 ? 'text-rose-400' : 'text-slate-200'}`}>
                {metrics.head_pitch.toFixed(1)}°
              </span>
            </div>
            <div>
              <span className="text-slate-500 block text-[10px]">Yaw</span>
              <span className="font-mono font-bold text-slate-200">{metrics.head_yaw.toFixed(1)}°</span>
            </div>
            <div>
              <span className="text-slate-500 block text-[10px]">Roll</span>
              <span className="font-mono font-bold text-slate-200">{metrics.head_roll.toFixed(1)}°</span>
            </div>
          </div>

          {/* Metric 5: KSS Fatigue Scale */}
          <div className="bg-slate-950 border border-slate-800/80 rounded-2xl p-3.5 flex items-center justify-between">
            <div>
              <span className="text-[10px] text-slate-500 uppercase font-semibold">Euro NCAP KSS Scale</span>
              <div className="text-lg font-extrabold text-white">
                {fusion.kss_now.toFixed(1)} <span className="text-xs text-slate-400 font-normal">/ 9.0</span>
              </div>
            </div>
            <span className={`px-2.5 py-1 text-xs font-bold rounded-lg ${
              fusion.kss_now >= 7 ? 'bg-rose-500/20 text-rose-400' : fusion.kss_now >= 6 ? 'bg-amber-500/20 text-amber-400' : 'bg-emerald-500/20 text-emerald-400'
            }`}>
              {fusion.kss_label}
            </span>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="text-center text-xs text-slate-500 py-1">
        Commercial Fleet Driver Monitoring System &bull; Session Active
      </footer>

      {/* End Trip Confirmation Modal */}
      {showEndModal && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6 sm:p-8 max-w-md w-full text-center shadow-2xl">
            <StopCircle className="w-12 h-12 text-rose-500 mx-auto mb-4" />
            <h3 className="text-xl font-bold text-white mb-2">End Monitoring Session?</h3>
            <p className="text-sm text-slate-400 mb-6">
              This will complete your commercial driving shift, update safety scoring metrics, and release hardware sensors.
            </p>
            <div className="flex gap-3 justify-center">
              <button
                disabled={ending}
                onClick={handleEndTrip}
                className="px-6 py-2.5 bg-rose-600 hover:bg-rose-500 text-white font-bold rounded-xl transition"
              >
                {ending ? 'Completing Shift...' : 'Yes, Complete Shift'}
              </button>
              <button
                disabled={ending}
                onClick={() => setShowEndModal(false)}
                className="px-6 py-2.5 bg-slate-800 hover:bg-slate-700 text-slate-300 font-semibold rounded-xl transition"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Trip Completed Summary Modal */}
      {tripSummary && (
        <div className="fixed inset-0 bg-black/85 backdrop-blur-md z-50 flex items-center justify-center p-4 animate-in fade-in duration-200">
          <div className="bg-slate-900 border border-emerald-500/40 rounded-3xl p-8 max-w-lg w-full text-center shadow-2xl">
            <CheckCircle2 className="w-14 h-14 text-emerald-400 mx-auto mb-4" />
            <h3 className="text-2xl font-bold text-white mb-1">Shift Completed Successfully</h3>
            <p className="text-xs text-slate-400 mb-6">Telemetry & incident logs archived to fleet records</p>

            <div className="bg-slate-950 border border-slate-800 rounded-2xl p-4 text-left text-sm space-y-2 mb-6">
              <div className="flex justify-between">
                <span className="text-slate-500">Driver:</span>
                <span className="font-semibold text-white">{tripSummary.driverName}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Vehicle:</span>
                <span className="font-semibold text-white">{tripSummary.vehicle}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Duration:</span>
                <span className="font-semibold text-cyan-400">{tripSummary.duration}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Final Fatigue Level:</span>
                <span className="font-semibold text-emerald-400">KSS {tripSummary.kssFinal.toFixed(1)} / 9.0</span>
              </div>
            </div>

            <button
              onClick={() => navigate('/driver')}
              className="w-full py-3.5 bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold rounded-xl transition"
            >
              Return to Cab Portal
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
