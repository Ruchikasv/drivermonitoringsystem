import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Play as PlayIcon, Square as StopIcon, RefreshCw as ArrowPathIcon } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';

const SCENARIOS = [
  { id: "NORMAL", label: "1. Normal Behavior", video: "1_normal.mp4" },
  { id: "NORMAL BLINK", label: "2. Normal Blinking", video: "2_normal_blink.mp4" },
  { id: "ACTIVE BLINKING", label: "3. Active/Frequent Blinking", video: "3_active_blink.mp4" },
  { id: "YAWNING", label: "4. Yawning", video: "4_yawning.mp4" },
  { id: "DROWSY", label: "5. Drowsy", video: "5_drowsy.mp4" },
  { id: "SLEEPY", label: "6. Sleepy / Prolonged Eye Closure", video: "6_sleepy.mp4" },
  { id: "CRITICAL DROWSINESS", label: "7. Deep Sleep / Critical Drowsiness", video: "7_critical.mp4" },
  { id: "RECOVERY", label: "8. Recovery / Awake", video: "8_recovery.mp4" },
  { id: "FUTURE_SENSORS", label: "9. Future Sensor (Alcohol/IR)", video: "1_normal.mp4", sensors: { alcohol_level: 0.12, alcohol_detected: true, ir_eye_confidence: 0.95 } }
];

const METRIC_THRESHOLDS = {
  ear: { min: 0.25, max: 0.35 },
  mar: { min: 0.0, max: 0.4 },
  perclos: { min: 0.0, max: 0.15 },
  pitch: { min: -15, max: 15 },
};

export default function SimulationPage() {
  const { token } = useAuth();
  const [scenarioId, setScenarioId] = useState(SCENARIOS[0].id);
  const [isRunning, setIsRunning] = useState(false);
  const [metrics, setMetrics] = useState(null);
  const [alertPayload, setAlertPayload] = useState(null);
  const [wsState, setWsState] = useState('DISCONNECTED');
  const [error, setError] = useState(null);
  const [annotatedFrame, setAnnotatedFrame] = useState(null);
  const [fps, setFps] = useState(0);
  
  const wsRef = useRef(null);
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const captureIntervalRef = useRef(null);
  const isSendingRef = useRef(false);
  
  // FPS tracking
  const frameCountRef = useRef(0);
  const lastFpsTimeRef = useRef(Date.now());

  const currentScenario = SCENARIOS.find(s => s.id === scenarioId) || SCENARIOS[0];

  const connectWS = useCallback(() => {
    if (wsRef.current) return;
    
    // Use session 999 for simulation
    const baseUrl = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000');
    const wsBaseUrl = baseUrl.replace(/^http/, 'ws');
    const wsUrl = `${wsBaseUrl}/ws/simulate/999`;
    
    try {
      const ws = new WebSocket(wsUrl);
      
      ws.onopen = () => {
        setWsState('CONNECTED');
        setError(null);
        if (isRunning) {
            ws.send(JSON.stringify({ type: 'SET_SCENARIO', scenario: scenarioId }));
        }
        startVideoProcessing(ws);
      };

      ws.onmessage = (event) => {
        isSendingRef.current = false;
        const data = JSON.parse(event.data);
        if (data.type === 'METRICS') {
          setMetrics(data.metrics);
          if (data.alert) {
              setAlertPayload(data.alert);
          }
          if (data.annotated_frame) {
              setAnnotatedFrame(`data:image/jpeg;base64,${data.annotated_frame}`);
              
              frameCountRef.current += 1;
              const now = Date.now();
              if (now - lastFpsTimeRef.current >= 1000) {
                  setFps(frameCountRef.current);
                  frameCountRef.current = 0;
                  lastFpsTimeRef.current = now;
              }
          }
        } else if (data.type === 'ERROR') {
            setError(data.message);
        }
      };

      ws.onclose = () => {
        setWsState('DISCONNECTED');
        wsRef.current = null;
        isSendingRef.current = false;
        stopVideoProcessing();
      };

      ws.onerror = (err) => {
        console.error('WS error:', err);
        setError('WebSocket error occurred');
        isSendingRef.current = false;
      };

      wsRef.current = ws;
    } catch (err) {
      setError(err.message);
    }
  }, [scenarioId, isRunning]);

  const disconnectWS = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    stopVideoProcessing();
  }, []);

  const startVideoProcessing = (ws) => {
      if (captureIntervalRef.current) clearInterval(captureIntervalRef.current);
      isSendingRef.current = false;
      
      if (videoRef.current) {
          videoRef.current.play().catch(e => {
              setError("Failed to play video. Check if video files exist in data/demo_videos.");
              console.error(e);
          });
      }

      captureIntervalRef.current = setInterval(() => {
        if (!videoRef.current || ws.readyState !== WebSocket.OPEN) return;
        if (isSendingRef.current || ws.bufferedAmount > 0) return;
        const video = videoRef.current;
        if (video.videoWidth === 0 || video.videoHeight === 0 || video.paused) return;

        if (!canvasRef.current) {
          canvasRef.current = document.createElement('canvas');
        }
        const canvas = canvasRef.current;
        // Keep 640x480 max size to match typical processing
        canvas.width = 640;
        canvas.height = 480;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(video, 0, 0, 640, 480);

        const b64 = canvas.toDataURL('image/jpeg', 0.60);
        isSendingRef.current = true;
        ws.send(JSON.stringify({ 
          frame: b64,
          sensors: currentScenario.sensors || {} 
        }));
      }, 85); // roughly 12 FPS like the production app
  };
  
  const stopVideoProcessing = () => {
      if (captureIntervalRef.current) {
          clearInterval(captureIntervalRef.current);
          captureIntervalRef.current = null;
      }
      if (videoRef.current) {
          videoRef.current.pause();
          videoRef.current.currentTime = 0;
      }
  };

  useEffect(() => {
    if (isRunning) {
        connectWS();
    } else {
        disconnectWS();
        setMetrics(null);
        setAlertPayload(null);
        setError(null);
        setAnnotatedFrame(null);
    }
    return () => disconnectWS();
  }, [isRunning, connectWS, disconnectWS]);

  useEffect(() => {
      if (isRunning && wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'SET_SCENARIO', scenario: scenarioId }));
        if (videoRef.current) {
            videoRef.current.currentTime = 0;
            videoRef.current.play().catch(e => console.error(e));
        }
      }
      setAlertPayload(null);
      setMetrics(null);
  }, [scenarioId, isRunning]);

  const handleStart = () => setIsRunning(true);
  const handleStop = () => setIsRunning(false);

  const handleReset = () => {
      setAlertPayload(null);
      setMetrics(null);
      setError(null);
      setAnnotatedFrame(null);
      if (isRunning && wsRef.current) {
        wsRef.current.send(JSON.stringify({ type: 'SET_SCENARIO', scenario: 'NORMAL' }));
        setScenarioId('NORMAL');
        if (videoRef.current) {
            videoRef.current.currentTime = 0;
            videoRef.current.play();
        }
      }
  };

  const getMetricColor = (val, threshold) => {
    if (!val || !threshold) return 'text-slate-200';
    if (val < threshold.min || val > threshold.max) return 'text-red-400 font-bold';
    return 'text-green-400';
  };

  const baseUrl = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000');

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="mb-6 pb-4 border-b border-slate-700/50 flex justify-between items-end">
        <div>
            <h1 className="text-2xl font-bold text-white mb-2 flex items-center gap-3">
            <span className="text-purple-400">⚡</span> 
            DEVELOPER / DMS DEMO MODE
            <span className="bg-purple-500/20 text-purple-400 text-xs px-2 py-1 rounded border border-purple-500/30">
                VIDEO-BASED PIPELINE
            </span>
            </h1>
            <p className="text-slate-400">Process real pre-recorded video frames through the actual production DMS pipeline.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Controls Panel */}
        <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-6 lg:col-span-1">
          <h2 className="text-lg font-semibold text-white mb-4">Demo Scenarios</h2>
          
          <div className="mb-6">
            <div className="grid grid-cols-1 gap-2">
              {SCENARIOS.map(s => (
                <button
                  key={s.id}
                  onClick={() => setScenarioId(s.id)}
                  disabled={isRunning && scenarioId === s.id}
                  className={`text-left px-3 py-2 rounded border text-sm transition-colors ${
                    scenarioId === s.id 
                      ? 'bg-blue-600 border-blue-500 text-white font-medium' 
                      : 'bg-slate-900 border-slate-700 text-slate-400 hover:bg-slate-800 hover:text-slate-200'
                  }`}
                >
                  {s.label}
                </button>
              ))}
            </div>
          </div>

          <div className="flex flex-col gap-3">
            {!isRunning ? (
              <button
                onClick={handleStart}
                className="w-full flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-500 text-white px-4 py-3 rounded-lg font-medium transition-colors"
              >
                <PlayIcon className="w-5 h-5" /> Start Pipeline
              </button>
            ) : (
              <button
                onClick={handleStop}
                className="w-full flex items-center justify-center gap-2 bg-red-600 hover:bg-red-500 text-white px-4 py-3 rounded-lg font-medium transition-colors"
              >
                <StopIcon className="w-5 h-5" /> Stop Pipeline
              </button>
            )}
            <button
              onClick={handleReset}
              className="w-full flex items-center justify-center gap-2 bg-slate-700 hover:bg-slate-600 text-white px-4 py-3 rounded-lg font-medium transition-colors"
            >
              <ArrowPathIcon className="w-5 h-5" /> Reset State
            </button>
          </div>

          <div className="mt-6 pt-6 border-t border-slate-700/50">
            <div className="flex items-center justify-between text-sm">
              <span className="text-slate-400">Connection:</span>
              <span className={`font-mono ${wsState === 'CONNECTED' ? 'text-green-400' : 'text-slate-500'}`}>
                {wsState}
              </span>
            </div>
            {error && (
              <div className="mt-3 p-3 bg-red-500/10 border border-red-500/20 text-red-400 text-sm rounded break-words">
                {error}
              </div>
            )}
          </div>
        </div>

        {/* Video & Telemetry Output */}
        <div className="lg:col-span-3 flex flex-col gap-6">
            
          {/* Video / Pipeline Output */}
          <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl overflow-hidden relative">
              
              {/* Hidden source video */}
              <video 
                ref={videoRef}
                src={`${baseUrl}/demo-videos/${currentScenario.video}`} 
                className="hidden"
                crossOrigin="anonymous"
                loop
                muted
                playsInline
              />

              <div className="aspect-video bg-black flex items-center justify-center relative">
                  {!isRunning ? (
                      <div className="text-slate-500 flex flex-col items-center">
                          <PlayIcon className="w-12 h-12 mb-2 opacity-50" />
                          <p>Select a scenario and click Start to process video.</p>
                      </div>
                  ) : annotatedFrame ? (
                      <img src={annotatedFrame} alt="Processed Frame" className="w-full h-full object-contain" />
                  ) : (
                      <div className="text-slate-400 animate-pulse">Initializing pipeline...</div>
                  )}

                  {/* Overlay metrics */}
                  {isRunning && (
                      <div className="absolute top-4 left-4 bg-black/60 backdrop-blur-sm border border-white/10 p-2 rounded text-xs font-mono text-white">
                          <div>SCENARIO: {currentScenario.id}</div>
                          <div className={fps < 10 ? 'text-red-400' : 'text-green-400'}>FPS: {fps}</div>
                      </div>
                  )}
              </div>
          </div>
            
          {/* Metrics Grid */}
          <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-6">
            <h2 className="text-lg font-semibold text-white mb-4">Pipeline Metrics</h2>
            
            {!metrics ? (
              <div className="h-16 flex items-center justify-center text-slate-500">
                Waiting for telemetry...
              </div>
            ) : (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <MetricBox label="EAR" value={metrics.ear} threshold={METRIC_THRESHOLDS.ear} />
                <MetricBox label="MAR" value={metrics.mar} threshold={METRIC_THRESHOLDS.mar} />
                <MetricBox label="PERCLOS" value={metrics.perclos} threshold={METRIC_THRESHOLDS.perclos} />
                <MetricBox label="Pitch" value={metrics.pitch} threshold={METRIC_THRESHOLDS.pitch} />
                <MetricBox label="CNN P(SLEEPY)" value={metrics.cnn_p_sleepy} />
                <MetricBox label="KSS" value={metrics.kss} />
                <MetricBox 
                  label="Risk Level" 
                  value={metrics.risk_level} 
                  className={metrics.risk_level === 'CRITICAL' ? 'text-red-400 font-bold' : 
                             metrics.risk_level === 'WARNING' ? 'text-orange-400' : 'text-slate-200'} 
                />
                <MetricBox label="Face Detected" value={metrics.face_detected ? 'YES' : 'NO'} />
              </div>
            )}
            
            {metrics?.extra_sensors && Object.keys(metrics.extra_sensors).length > 0 && (
              <div className="mt-4 pt-4 border-t border-slate-700/50">
                <h3 className="text-sm font-semibold text-slate-400 mb-3">Simulated External Sensors</h3>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  {Object.entries(metrics.extra_sensors).map(([key, value]) => (
                    <MetricBox 
                      key={key} 
                      label={key.replace(/_/g, ' ').toUpperCase()} 
                      value={typeof value === 'boolean' ? (value ? 'YES' : 'NO') : value} 
                    />
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Alert State */}
          <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl p-6">
              <h2 className="text-lg font-semibold text-white mb-4">Alert State</h2>
              {alertPayload ? (
                <div className="bg-slate-900 border border-slate-700 rounded p-4 font-mono text-sm overflow-auto text-green-400">
                  <div className="mb-2 flex flex-wrap items-center gap-2">
                    <span className="text-white font-bold mr-auto">Generated Alert Payload</span>
                    <span className="px-2 py-1 bg-green-900/50 text-green-300 rounded text-xs border border-green-700/50">
                      Incident Emitted
                    </span>
                    <span className="px-2 py-1 bg-green-900/50 text-green-300 rounded text-xs border border-green-700/50">
                      Evidence Recorded
                    </span>
                    {alertPayload.action === "SOUND_SIREN" && (
                        <span className="px-2 py-1 bg-red-900/50 text-red-300 rounded text-xs border border-red-700/50 animate-pulse">
                            Siren Active
                        </span>
                    )}
                  </div>
                  <pre>{JSON.stringify(alertPayload, null, 2)}</pre>
                </div>
              ) : (
                 <div className="h-20 flex items-center justify-center text-slate-500 bg-slate-900/50 border border-slate-700 rounded">
                    No active alert payload generated.
                 </div>
              )}
          </div>

        </div>
      </div>
    </div>
  );
}

function MetricBox({ label, value, threshold, className }) {
  let displayColor = 'text-slate-200';
  if (threshold && value !== undefined) {
      if (value < threshold.min || value > threshold.max) {
          displayColor = 'text-red-400 font-bold';
      } else {
          displayColor = 'text-green-400';
      }
  }
  
  return (
    <div className="bg-slate-900 border border-slate-700 p-3 rounded text-center">
      <div className="text-xs text-slate-400 mb-1">{label}</div>
      <div className={`text-xl font-mono ${className || displayColor}`}>
        {value !== undefined ? value : '--'}
      </div>
    </div>
  );
}
