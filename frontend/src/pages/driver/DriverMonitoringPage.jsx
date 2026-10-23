import React, { useState, useEffect, useRef } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import {
  ShieldCheck,
  AlertTriangle,
  Flame,
  StopCircle,
  Pause,
  Play,
  Eye,
  Smile,
  Activity,
  Compass,
  CheckCircle2,
  Clock,
  Smartphone,
  Loader2,
} from 'lucide-react';
import { monitoringService } from '../../services/monitoringService';
import { soundManager } from '../../utils/soundManager';
import AlcoholSafetyWarning from '../../components/driver/AlcoholSafetyWarning';

export default function DriverMonitoringPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const sessionId = searchParams.get('session');
  const driverId = searchParams.get('driver');
  const sessionToken = searchParams.get('token');

  const [sessionLoading, setSessionLoading] = useState(true);
  const [sessionError, setSessionError] = useState(null);
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
    face_detected: false,
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
  const [tripSummary, setTripSummary] = useState(null);
  const [showEndModal, setShowEndModal] = useState(false);
  const [ending, setEnding] = useState(false);
  const [pausing, setPausing] = useState(false);
  const [cameras, setCameras] = useState([]);
  const [selectedCameraId, setSelectedCameraId] = useState('');
  const [cameraType, setCameraType] = useState('rgb');
  const [debugMode, setDebugMode] = useState(false);
  const [debugTab, setDebugTab] = useState('all');
  const [debugData, setDebugData] = useState(null);
  const [fps, setFps] = useState(0);

  const wsRef = useRef(null);
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);
  const captureIntervalRef = useRef(null);
  const isSendingRef = useRef(false);
  const startTimeRef = useRef(Date.now());
  const cameraTypeRef = useRef('rgb');
  const debugModeRef = useRef(false);
  const framesCountRef = useRef(0);
  const lastFpsTimeRef = useRef(Date.now());
  const wsSentCountRef = useRef(0);
  const wsRecvCountRef = useRef(0);

  /** Detect if a camera label looks like a USB/IR/infrared camera. */
  const detectIrCamera = (label) => {
    if (!label) return false;
    const l = label.toLowerCase();
    return l.includes('ir') || l.includes('infrared') || l.includes('usb') || /\([0-9a-f]{4}:[0-9a-f]{4}\)/.test(l);
  };

  const stopWebcam = () => {
    // DO NOT clear the capture interval here; it is tied to the WebSocket lifecycle.
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

  const startWebcam = async (deviceId = null) => {
    stopWebcam();
    setCameraError(null);
    console.log('[DMS Camera] startWebcam called, deviceId:', deviceId);
    try {
      const constraints = {
        video: { width: { ideal: 640 }, height: { ideal: 480 } },
        audio: false,
      };
      if (deviceId) {
        constraints.video.deviceId = { exact: deviceId };
      } else {
        constraints.video.facingMode = 'user';
      }
      const stream = await navigator.mediaDevices.getUserMedia(constraints);
      streamRef.current = stream;
      const track = stream.getVideoTracks()[0];
      console.log('STREAM_STARTED', track?.label, 'settings:', track?.getSettings());
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        videoRef.current.onloadedmetadata = () => {
          videoRef.current.play().catch(() => {});
          console.log('VIDEO_READY', 'videoWidth:', videoRef.current.videoWidth, 'videoHeight:', videoRef.current.videoHeight, 'readyState:', videoRef.current.readyState);
          setCameraReady(true);
        };
      }
    } catch (err) {
      console.error('[DMS Camera] Monitoring webcam error:', err);
      setCameraError('Unable to access monitoring webcam. Please ensure camera permissions are granted.');
    }
  };

  useEffect(() => {
    if (!sessionId) {
      navigate('/driver');
      return;
    }

    let isCancelled = false;
    let wsInstance = null;

    const startSessionWorkflow = async () => {
      setSessionLoading(true);
      setSessionError(null);

      try {
        const sess = await monitoringService.getSession(sessionId, sessionToken);
        if (isCancelled) return;

        if (!sess) {
          setSessionError('Monitoring session record not found.');
          setSessionLoading(false);
          return;
        }

        if (sess.is_locked) {
          setIsPaused(true);
          setSessionError('VEHICLE OPERATION LOCKED OUT: Potential alcohol detected. Trip operation is restricted.');
          setSessionLoading(false);
          return;
        }

        if (sess.status === 'PAUSED') {
          setIsPaused(true);
        } else if (sess.status === 'COMPLETED' || sess.status === 'INTERRUPTED') {
          setSessionError(`Trip monitoring has ended (status: ${sess.status}).`);
          setSessionLoading(false);
          return;
        }

        setSessionLoading(false);
        await initCamerasAndStream();
      } catch (err) {
        if (isCancelled) return;
        console.error('Session verification error:', err);
        setSessionLoading(false);

        if (err.response?.status === 423) {
          setIsPaused(true);
          setSessionError(err.response.data?.detail || 'VEHICLE OPERATION LOCKED OUT: Potential alcohol detected.');
          return;
        }

        const msg = err.response?.data?.detail
          || (err.message === 'Network Error' || err.code === 'ERR_NETWORK'
              ? 'Unable to connect to Fleet Safety DMS server. Please verify the backend is running on port 8000.'
              : err.message)
          || 'Failed to initialize driver monitoring session.';
        setSessionError(msg);
      }
    };

    const initCamerasAndStream = async () => {
      try {
        // Trigger camera permission (we immediately stop this temp stream)
        const tempStream = await navigator.mediaDevices.getUserMedia({ video: true });
        tempStream.getTracks().forEach((t) => t.stop());
        const devices = await navigator.mediaDevices.enumerateDevices();
        const videoDevices = devices.filter((d) => d.kind === 'videoinput');
        console.log('[DMS Camera] Enumerated cameras:', videoDevices.map((d) => ({ label: d.label, deviceId: d.deviceId })));
        setCameras(videoDevices);
        if (videoDevices.length > 0 && !selectedCameraId) {
          const firstDevice = videoDevices[0];
          const isIr = detectIrCamera(firstDevice.label);
          setCameraType(isIr ? 'ir' : 'rgb');
          cameraTypeRef.current = isIr ? 'ir' : 'rgb';
          console.log('CAMERA_SELECTED', firstDevice.label, '| type:', isIr ? 'ir' : 'rgb');
          setSelectedCameraId(firstDevice.deviceId);
        } else {
          startWebcam(); // fallback
        }
      } catch (err) {
        console.error('[DMS Camera] Error enumerating devices', err);
        startWebcam();
      }

      if (isCancelled) return;

      const token = searchParams.get('token');
      const wsUrl = monitoringService.getWebSocketUrl(sessionId, token);
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;
      wsInstance = ws;

      ws.onopen = () => {
        if (isCancelled) {
          ws.close();
          return;
        }
        setConnected(true);
        console.log('Connected to driver monitoring WebSocket:', sessionId);

        // Flow-controlled frame transmission to backend (no queue backlog)
        if (captureIntervalRef.current) clearInterval(captureIntervalRef.current);
        isSendingRef.current = false;
        captureIntervalRef.current = setInterval(() => {
          if (!videoRef.current || ws.readyState !== WebSocket.OPEN) return;
          if (isSendingRef.current || ws.bufferedAmount > 0) return;
          const video = videoRef.current;
          if (video.videoWidth === 0 || video.videoHeight === 0 || video.paused || video.readyState < 2) return;

          if (!canvasRef.current) {
            canvasRef.current = document.createElement('canvas');
          }
          const canvas = canvasRef.current;
          canvas.width = 640;
          canvas.height = 480;
          const ctx = canvas.getContext('2d');
          ctx.drawImage(video, 0, 0, 640, 480);
          console.log('FRAME_CAPTURED');

          const b64 = canvas.toDataURL('image/jpeg', 0.60);
          isSendingRef.current = true;
          wsSentCountRef.current += 1;
          
          framesCountRef.current += 1;
          const now = Date.now();
          if (now - lastFpsTimeRef.current >= 1000) {
            const currentFps = Math.round((framesCountRef.current * 1000) / (now - lastFpsTimeRef.current));
            setFps(currentFps);
            console.log(`[DMS Pipeline] FPS: ${currentFps} | Sent: ${wsSentCountRef.current} | Recv: ${wsRecvCountRef.current} | camera_type: ${cameraTypeRef.current} | videoW: ${video.videoWidth} videoH: ${video.videoHeight} readyState: ${video.readyState}`);
            framesCountRef.current = 0;
            lastFpsTimeRef.current = now;
          }

          ws.send(JSON.stringify({ 
            frame: b64, 
            camera_type: cameraTypeRef.current,
            debug_mode: debugModeRef.current
          }));
          console.log('FRAME_SENT');
        }, 85);
      };

      ws.onmessage = (event) => {
        isSendingRef.current = false;
        wsRecvCountRef.current += 1;
        console.log('FRAME_RECEIVED');
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
            console.log('PROCESSED_FRAME_RENDERED');
          }

          if (data.metrics) {
            setMetrics(data.metrics);
          }

          if (data.fusion) {
            setFusion(data.fusion);
          }

          if (data.debug_data) {
            setDebugData((prev) => ({
              ...prev,
              ...data.debug_data,
              left_eye: data.debug_data.left_eye || prev?.left_eye,
              right_eye: data.debug_data.right_eye || prev?.right_eye,
            }));
          }

          // Sync camera type from backend response if provided
          const responseCameraType = data.camera_type || data.fusion?.camera_type;
          if (responseCameraType) {
            setCameraType(responseCameraType);
            cameraTypeRef.current = responseCameraType;
          }

          const isCriticalActive = Boolean(data.critical_active) && !data.is_paused;

          if (isCriticalActive) {
            soundManager.playAlert("critical");
          } else {
            // If critical is no longer active, ensure critical siren is stopped
            if (soundManager.isCriticalPlaying) {
              soundManager.stopCriticalSiren();
            }

            // Handle one-shot warning / nudge alerts if present (keep distraction alerts independent)
            if (data.alert && !data.is_paused && data.alert.event_type !== "distraction") {
              if (data.alert.tier === "warning") {
                soundManager.playAlert("warning");
              } else if (data.alert.tier === "nudge") {
                soundManager.playAlert("nudge");
              }
            }
          }

          // Distraction alert audio (independent from drowsiness tiers)
          const isDistractionTriggered = (data.distraction?.triggered || data.metrics?.distraction_triggered) && !data.is_paused;
          if (isDistractionTriggered) {
            soundManager.playDistractionBeep(true);
          }

          if (data.alert && !data.is_paused) {
            setCurrentAlert(data.alert);
          } else if (!isCriticalActive && !data.metrics?.distraction_confirmed) {
            setCurrentAlert(null);
          }
        } catch (err) {
          console.error('WebSocket message parsing error:', err);
        }
      };

      ws.onerror = () => {
        isSendingRef.current = false;
        console.error('Driver monitoring WebSocket error');
      };

      ws.onclose = () => {
        isSendingRef.current = false;
        setConnected(false);
        console.log('Driver monitoring WebSocket closed.');
      };
    };

    startSessionWorkflow();

    return () => {
      isCancelled = true;
      if (captureIntervalRef.current) {
        clearInterval(captureIntervalRef.current);
        captureIntervalRef.current = null;
      }
      stopWebcam();
      soundManager.stop();
      if (wsInstance && (wsInstance.readyState === WebSocket.OPEN || wsInstance.readyState === WebSocket.CONNECTING)) {
        wsInstance.close();
      }
    };
  }, [sessionId]);

  useEffect(() => {
    if (selectedCameraId) {
      // Also update camera type when switching cameras
      const cam = cameras.find(c => c.deviceId === selectedCameraId);
      if (cam) {
        const isIr = detectIrCamera(cam.label);
        setCameraType(isIr ? 'ir' : 'rgb');
        cameraTypeRef.current = isIr ? 'ir' : 'rgb';
        console.log('[DMS Camera] Camera switched to:', cam.label, '| type:', isIr ? 'ir' : 'rgb', '| deviceId:', selectedCameraId);
      }
      startWebcam(selectedCameraId);
    }
  }, [selectedCameraId]);

  const handlePauseTrip = async () => {
    setPausing(true);
    try {
      soundManager.stop();
      setCurrentAlert(null);
      await monitoringService.pauseSession(sessionId, sessionToken);
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
      await monitoringService.resumeSession(sessionId, sessionToken);
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
      await monitoringService.endSession(sessionId, sessionToken);

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
  const isDistraction = !isPaused && !isCritical && (metrics.distraction_confirmed || currentAlert?.event_type === 'distraction');
  const isWarning = !isPaused && !isCritical && !isDistraction && (fusion.kss_now >= 6.0 || currentAlert?.tier === 'warning' || metrics.yawn_active);
  const isNudge = !isPaused && !isCritical && !isWarning && !isDistraction && (fusion.kss_now >= 4.5 || currentAlert?.tier === 'nudge' || metrics.perclos >= 0.20);

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
  } else if (isDistraction) {
    statusBg = 'bg-purple-500/20 border-purple-500/50 text-purple-300 animate-pulse';
    statusTitle = 'DISTRACTION DETECTED — PHONE USAGE';
    statusSubtitle = 'Driver looking down at mobile phone — Keep eyes on the road!';
    statusIcon = <Smartphone className="w-5 h-5 text-purple-400 animate-bounce" />;
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

  if (sessionLoading) {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col items-center justify-center p-6 font-sans">
        <div className="bg-slate-900 border border-slate-800 rounded-3xl p-8 max-w-md w-full text-center shadow-2xl flex flex-col items-center gap-4">
          <Loader2 className="w-12 h-12 text-cyan-400 animate-spin" />
          <h2 className="text-xl font-bold tracking-wide text-white">Validating Safety Session</h2>
          <p className="text-sm text-slate-400">Connecting to Fleet Safety DMS server and verifying active trip authorization...</p>
        </div>
      </div>
    );
  }

  if (sessionError) {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col items-center justify-center p-6 font-sans">
        <div className="bg-slate-900 border border-rose-500/30 rounded-3xl p-8 max-w-lg w-full text-center shadow-2xl flex flex-col items-center gap-5">
          <div className="w-16 h-16 rounded-2xl bg-rose-500/10 border border-rose-500/30 flex items-center justify-center text-rose-400">
            <AlertTriangle className="w-8 h-8" />
          </div>
          <div className="space-y-2">
            <h2 className="text-xl font-bold tracking-wide text-rose-300">Safety Verification Notice</h2>
            <p className="text-sm text-slate-300 leading-relaxed bg-slate-950/60 p-3 rounded-xl border border-slate-800 font-mono text-left break-words">
              {sessionError}
            </p>
          </div>
          <div className="flex items-center gap-3 w-full pt-2">
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="flex-1 py-3 px-4 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 font-semibold text-sm transition"
            >
              Retry Connection
            </button>
            <button
              type="button"
              onClick={() => navigate('/driver')}
              className="flex-1 py-3 px-4 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-white font-semibold text-sm shadow-lg shadow-cyan-600/30 transition"
            >
              Return to Cab Portal
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col justify-between p-4 sm:p-6 font-sans select-none">
      <header className="flex justify-between items-center bg-slate-900 border border-slate-800 rounded-3xl p-3 sm:px-6 shadow-2xl mb-4">
        <div className="flex items-center gap-3">
          <select 
            className="bg-slate-800 text-xs text-white px-2 py-1 rounded border border-slate-700 outline-none" 
            value={selectedCameraId}
            onChange={(e) => {
              const newDeviceId = e.target.value;
              const label = e.target.options[e.target.selectedIndex].text;
              const isIr = detectIrCamera(label);
              console.log('[DMS Camera] User selected camera:', label, '| deviceId:', newDeviceId, '| IR:', isIr);
              setCameraType(isIr ? 'ir' : 'rgb');
              cameraTypeRef.current = isIr ? 'ir' : 'rgb';
              setSelectedCameraId(newDeviceId);
            }}
          >
            {cameras.map(cam => (
              <option key={cam.deviceId} value={cam.deviceId}>{cam.label || `Camera ${cam.deviceId}`}</option>
            ))}
          </select>
          <button 
             type="button"
             onClick={() => {
               if (debugMode && debugTab === 'ir') {
                 setDebugMode(false);
                 debugModeRef.current = false;
               } else {
                 setDebugMode(true);
                 setDebugTab('ir');
                 debugModeRef.current = true;
               }
             }} 
             className={`text-xs px-2.5 py-1 rounded-lg border font-bold transition flex items-center gap-1.5 ${debugMode && (debugTab === 'ir' || debugTab === 'all') ? 'bg-indigo-600 border-indigo-500 text-white shadow-md shadow-indigo-600/30' : 'bg-slate-800 border-slate-700 text-slate-400 hover:text-white'}`}
          >
             <span className={`w-2 h-2 rounded-full ${debugMode && (debugTab === 'ir' || debugTab === 'all') ? 'bg-cyan-400 animate-pulse' : 'bg-slate-500'}`} />
             IR Debug
          </button>
          <button 
             type="button"
             onClick={() => {
               if (debugMode && debugTab === 'cnn') {
                 setDebugMode(false);
                 debugModeRef.current = false;
               } else {
                 setDebugMode(true);
                 setDebugTab('cnn');
                 debugModeRef.current = true;
               }
             }} 
             className={`text-xs px-2.5 py-1 rounded-lg border font-bold transition flex items-center gap-1.5 ${debugMode && (debugTab === 'cnn' || debugTab === 'all') ? 'bg-cyan-600 border-cyan-500 text-white shadow-md shadow-cyan-600/30' : 'bg-slate-800 border-slate-700 text-slate-400 hover:text-white'}`}
          >
             <span className={`w-2 h-2 rounded-full ${debugMode && (debugTab === 'cnn' || debugTab === 'all') ? 'bg-emerald-400 animate-pulse' : 'bg-slate-500'}`} />
             CNN Section
          </button>
          <AlcoholSafetyWarning sessionId={sessionId} showBadge={true} />
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
              className="hidden"
            />
            {frameB64 ? (
              <img src={`data:image/jpeg;base64,${frameB64}`} className="w-full h-full object-cover" />
            ) : (
              <div className="text-slate-500 text-sm font-semibold">Awaiting processed frame...</div>
            )}

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
              {metrics.distraction_confirmed && (
                <span className="px-3 py-1 bg-purple-600 text-white font-bold text-xs rounded-lg shadow-lg animate-pulse flex items-center gap-1.5">
                  <Smartphone className="w-3.5 h-3.5" /> PROLONGED PHONE DISTRACTION ({metrics.distraction_duration ? metrics.distraction_duration.toFixed(1) : '2.0'}s)
                </span>
              )}
              {!metrics.distraction_confirmed && metrics.distraction_active && (
                <span className="px-3 py-1 bg-amber-600/90 text-white font-semibold text-xs rounded-lg shadow-lg flex items-center gap-1.5">
                  <Smartphone className="w-3.5 h-3.5" /> PHONE DISTRACTION DETECTING ({metrics.distraction_duration ? metrics.distraction_duration.toFixed(1) : '0.0'}s)
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

            {debugMode && (
              <div className="absolute left-4 bottom-4 bg-slate-950/95 backdrop-blur-md p-4 rounded-2xl border border-indigo-500/50 text-[10px] font-mono text-cyan-400 z-20 flex flex-col gap-3 shadow-2xl min-w-[320px] max-w-[380px]">
                 <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                   <div className="font-bold text-indigo-400 tracking-wider flex items-center gap-1.5">
                     <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
                     {debugTab === 'ir' ? 'IR HARDWARE VALIDATION' : debugTab === 'cnn' ? 'EYE CNN SLEEPINESS MODEL' : 'IR HARDWARE & CNN VALIDATION'}
                   </div>
                   <div className="flex items-center gap-1.5">
                     <div className="flex bg-slate-900 border border-slate-800 rounded-lg p-0.5 text-[9px]">
                       <button
                         type="button"
                         onClick={() => setDebugTab('all')}
                         className={`px-1.5 py-0.5 rounded ${debugTab === 'all' ? 'bg-indigo-600 text-white font-bold' : 'text-slate-400 hover:text-white'}`}
                       >
                         ALL
                       </button>
                       <button
                         type="button"
                         onClick={() => setDebugTab('ir')}
                         className={`px-1.5 py-0.5 rounded ${debugTab === 'ir' ? 'bg-indigo-600 text-white font-bold' : 'text-slate-400 hover:text-white'}`}
                       >
                         IR
                       </button>
                       <button
                         type="button"
                         onClick={() => setDebugTab('cnn')}
                         className={`px-1.5 py-0.5 rounded ${debugTab === 'cnn' ? 'bg-cyan-600 text-white font-bold' : 'text-slate-400 hover:text-white'}`}
                       >
                         CNN
                       </button>
                     </div>
                     <button 
                       type="button"
                       onClick={() => {
                         setDebugMode(false);
                         debugModeRef.current = false;
                       }}
                       className="text-slate-500 hover:text-white px-1.5 py-0.5 rounded bg-slate-900 border border-slate-800 text-[9px]"
                     >
                       ✕
                     </button>
                   </div>
                 </div>
                 
                 {(debugTab === 'all' || debugTab === 'ir') && (
                   <div className="grid grid-cols-2 gap-x-4 gap-y-1 border-b border-slate-800 pb-2">
                     <div>FACE DETECTED: <span className={metrics.face_detected ? "text-emerald-400 font-bold" : "text-rose-400 font-bold"}>{metrics.face_detected ? 'YES' : 'NO'}</span></div>
                     <div>FPS: <span className="text-white font-bold">{fps}</span></div>
                     <div>EAR: <span className="text-white">{metrics.ear?.toFixed(3)}</span></div>
                     <div>MAR: <span className="text-white">{metrics.mar?.toFixed(3)}</span></div>
                     <div>PERCLOS: <span className="text-white">{((metrics.perclos || 0) * 100).toFixed(1)}%</span></div>
                     <div>PITCH: <span className="text-white">{metrics.head_pitch?.toFixed(1)}°</span></div>
                   </div>
                 )}

                 {(debugTab === 'all' || debugTab === 'cnn') && (
                   <>
                     <div className="flex gap-4 border-b border-slate-800 pb-2 justify-center">
                       <div className="text-center">
                         <div className="text-slate-400 mb-1 text-[9px] tracking-wider font-semibold">LEFT EYE CROP</div>
                         {debugData?.left_eye ? (
                           <img src={`data:image/jpeg;base64,${debugData.left_eye}`} alt="Left Eye" className="w-20 h-20 object-cover border border-slate-700 mx-auto rounded-lg shadow-sm" />
                         ) : (
                           <div className="w-20 h-20 bg-slate-900/80 border border-slate-800 mx-auto rounded-lg flex items-center justify-center text-slate-500 text-[9px] text-center px-1">
                             {metrics.face_detected ? 'Cropping...' : 'No Face'}
                           </div>
                         )}
                         <div className="mt-1">P(Sleepy): <span className="text-white font-bold">{debugData?.cnn_p_left !== undefined ? debugData.cnn_p_left.toFixed(3) : (metrics.extra_sensors?.cnn_p_left !== undefined ? metrics.extra_sensors.cnn_p_left.toFixed(3) : '-')}</span></div>
                       </div>
                       <div className="text-center">
                         <div className="text-slate-400 mb-1 text-[9px] tracking-wider font-semibold">RIGHT EYE CROP</div>
                         {debugData?.right_eye ? (
                           <img src={`data:image/jpeg;base64,${debugData.right_eye}`} alt="Right Eye" className="w-20 h-20 object-cover border border-slate-700 mx-auto rounded-lg shadow-sm" />
                         ) : (
                           <div className="w-20 h-20 bg-slate-900/80 border border-slate-800 mx-auto rounded-lg flex items-center justify-center text-slate-500 text-[9px] text-center px-1">
                             {metrics.face_detected ? 'Cropping...' : 'No Face'}
                           </div>
                         )}
                         <div className="mt-1">P(Sleepy): <span className="text-white font-bold">{debugData?.cnn_p_right !== undefined ? debugData.cnn_p_right.toFixed(3) : (metrics.extra_sensors?.cnn_p_right !== undefined ? metrics.extra_sensors.cnn_p_right.toFixed(3) : '-')}</span></div>
                       </div>
                     </div>

                     <div className="grid grid-cols-1 gap-1">
                       <div className="flex justify-between">
                         <span>AVG CNN P(SLEEPY):</span>
                         <span className={`font-bold ${(metrics.fusion?.cnn_p_sleepy || 0) > 0.5 ? 'text-amber-400' : 'text-emerald-400'}`}>
                           {(metrics.fusion?.cnn_p_sleepy !== undefined ? metrics.fusion.cnn_p_sleepy.toFixed(3) : (metrics.extra_sensors?.cnn_p_sleepy !== undefined ? metrics.extra_sensors.cnn_p_sleepy.toFixed(3) : '0.000'))} 
                           <span className="ml-1.5">({(metrics.fusion?.cnn_p_sleepy || 0) > 0.5 ? 'SLEEPY' : 'AWAKE'})</span>
                         </span>
                       </div>
                       <div className="flex justify-between text-slate-400">
                         <span>CNN INFERENCE LATENCY:</span>
                         <span className="text-white">{metrics.cnn_latency_ms !== undefined ? metrics.cnn_latency_ms.toFixed(1) : (metrics.extra_sensors?.cnn_latency_ms !== undefined ? metrics.extra_sensors.cnn_latency_ms.toFixed(1) : '0.0')} ms</span>
                       </div>
                       <div className="flex justify-between text-slate-400">
                         <span>TOTAL PIPELINE LATENCY:</span>
                         <span className="text-white">{metrics.total_latency_ms ? metrics.total_latency_ms.toFixed(1) : '0.0'} ms</span>
                       </div>
                     </div>
                   </>
                 )}
              </div>
            )}

            {/* Subtle Camera HUD Corner markings */}
            <div className="absolute top-3 right-3 text-[10px] font-mono text-cyan-400/80 bg-slate-950/70 px-2 py-1 rounded-md border border-cyan-500/20 pointer-events-none flex flex-col items-end gap-1 z-10 shadow-lg">
              <div>{isPaused ? 'MONITORING SUSPENDED' : `FACIAL MESH • 478 PTS`}</div>
              <div>CAMERA: <span className="text-white font-bold">{cameraType === 'ir' ? 'USB IR' : 'RGB Webcam'}</span></div>
              <div>FACE DETECTED: <span className={metrics.face_detected ? "text-emerald-400 font-bold" : "text-rose-400 font-bold"}>{metrics.face_detected ? 'YES' : 'NO'}</span></div>
              <div>FPS: {fps} | Latency: {metrics.total_latency_ms || 0} ms</div>
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

          {/* Metric 5: Phone Distraction Telemetry */}
          <div className="bg-slate-950 border border-slate-800/80 rounded-2xl p-3.5">
            <div className="flex justify-between text-xs mb-1.5">
              <span className="text-slate-400 font-semibold flex items-center gap-1.5">
                <Smartphone className="w-3.5 h-3.5 text-purple-400" /> Phone Distraction
              </span>
              <span className={`font-mono font-bold ${metrics.distraction_confirmed ? 'text-purple-400 animate-pulse' : metrics.distraction_active ? 'text-amber-400' : metrics.phone_detected ? 'text-cyan-400' : 'text-slate-400'}`}>
                {metrics.distraction_confirmed
                  ? `CONFIRMED (${metrics.distraction_duration ? metrics.distraction_duration.toFixed(1) : '2.0'}s)`
                  : metrics.distraction_active
                  ? `DETECTING (${metrics.distraction_duration ? metrics.distraction_duration.toFixed(1) : '0.0'}s)`
                  : metrics.phone_detected
                  ? `PHONE PRESENT (${(metrics.phone_confidence * 100).toFixed(0)}%)`
                  : 'ATTENTIVE'}
              </span>
            </div>
            <div className="flex justify-between text-[10px] text-slate-500 mt-1">
              <span>Object: {metrics.phone_detected ? `Cell phone (${(metrics.phone_confidence * 100).toFixed(0)}%)` : 'None in view'}</span>
              <span>Head Tilt: {metrics.head_pitch.toFixed(1)}°</span>
            </div>
          </div>

          {/* Metric 6: CNN Eye Sleepiness Model */}
          <div className="bg-slate-950 border border-slate-800/80 rounded-2xl p-3.5">
            <div className="flex justify-between text-xs mb-1.5">
              <span className="text-slate-400 font-semibold flex items-center gap-1.5">
                <Eye className="w-3.5 h-3.5 text-indigo-400" /> CNN Eye State (Sleepiness)
              </span>
              <span className={`font-mono font-bold ${(metrics.fusion?.cnn_p_sleepy || metrics.extra_sensors?.cnn_p_sleepy || 0) > 0.5 ? 'text-amber-400' : 'text-emerald-400'}`}>
                {(((metrics.fusion?.cnn_p_sleepy ?? metrics.extra_sensors?.cnn_p_sleepy ?? 0)) * 100).toFixed(1)}% {((metrics.fusion?.cnn_p_sleepy ?? metrics.extra_sensors?.cnn_p_sleepy ?? 0)) > 0.5 ? 'SLEEPY' : 'AWAKE'}
              </span>
            </div>
            <div className="w-full h-2 bg-slate-800 rounded-full overflow-hidden">
              <div
                className={`h-full transition-all duration-100 ${((metrics.fusion?.cnn_p_sleepy ?? metrics.extra_sensors?.cnn_p_sleepy ?? 0)) > 0.5 ? 'bg-amber-500' : 'bg-indigo-500'}`}
                style={{ width: `${Math.min(100, ((metrics.fusion?.cnn_p_sleepy ?? metrics.extra_sensors?.cnn_p_sleepy ?? 0)) * 100)}%` }}
              />
            </div>
            <div className="flex justify-between text-[10px] text-slate-500 mt-1">
              <span>Model: ONNX 32×32 Grayscale</span>
              <span>Latency: {metrics.cnn_latency_ms ? `${metrics.cnn_latency_ms.toFixed(1)}ms` : (metrics.extra_sensors?.cnn_latency_ms ? `${metrics.extra_sensors.cnn_latency_ms.toFixed(1)}ms` : '<2ms')}</span>
            </div>
          </div>

          {/* Metric 7: KSS Fatigue Scale */}
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
