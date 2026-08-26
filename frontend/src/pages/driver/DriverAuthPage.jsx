import React, { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Camera, ArrowLeft, CheckCircle2, AlertCircle, Loader2, RefreshCw, Truck, ShieldAlert } from 'lucide-react';
import { authService } from '../../services/authService';
import { monitoringService } from '../../services/monitoringService';

export default function DriverAuthPage() {
  const navigate = useNavigate();
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);

  const [cameraActive, setCameraActive] = useState(false);
  const [authenticating, setAuthenticating] = useState(false);
  const [startingSession, setStartingSession] = useState(false);
  const [authResult, setAuthResult] = useState(null);
  const [errorMsg, setErrorMsg] = useState(null);

  // Explicitly release browser camera stream
  const stopCamera = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => {
        track.stop();
      });
      streamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    setCameraActive(false);
  };

  const startCamera = async () => {
    stopCamera();
    setErrorMsg(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' },
        audio: false,
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }
      setCameraActive(true);
    } catch (err) {
      console.error('Camera error:', err);
      setErrorMsg('Could not access webcam. Please ensure camera permissions are enabled.');
      setCameraActive(false);
    }
  };

  useEffect(() => {
    startCamera();
    return () => {
      stopCamera();
    };
  }, []);

  const handleAuthenticate = async () => {
    if (!videoRef.current || !canvasRef.current) return;

    setErrorMsg(null);
    setAuthenticating(true);

    try {
      const canvas = canvasRef.current;
      const video = videoRef.current;
      canvas.width = video.videoWidth || 640;
      canvas.height = video.videoHeight || 480;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

      const frameB64 = canvas.toDataURL('image/jpeg', 0.85);
      const res = await authService.authenticateDriver(frameB64);
      
      // Stop authentication camera stream immediately upon success
      stopCamera();
      setAuthResult(res);

      if (res.vehicle_id) {
        // Auto-launch monitoring session after brief verification display
        setTimeout(() => {
          handleStartShift(res);
        }, 1200);
      }
    } catch (err) {
      console.error('Authentication error:', err);
      const detail = err.response?.data?.detail || 'Authentication failed. Please position face clearly.';
      setErrorMsg(detail);
    } finally {
      setAuthenticating(false);
    }
  };

  const handleStartShift = async (targetAuth = authResult) => {
    if (!targetAuth || !targetAuth.vehicle_id) return;

    setStartingSession(true);
    setErrorMsg(null);

    try {
      // 1. Explicitly stop and release browser camera stream
      stopCamera();

      // Short delay to guarantee hardware driver release
      await new Promise((r) => setTimeout(r, 150));

      // 2. Create session in backend
      const session = await monitoringService.createSession(
        targetAuth.driver_id,
        targetAuth.vehicle_id
      );

      // 3. Navigate to monitoring page
      navigate(`/driver/monitoring?session=${session.session_id}&driver=${targetAuth.driver_id}`);
    } catch (err) {
      console.error('Failed to create session:', err);
      setErrorMsg(err.response?.data?.detail || 'Failed to start monitoring session. Try again.');
      setStartingSession(false);
      startCamera();
    }
  };


  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col p-6 sm:p-10 font-sans">
      <header className="flex items-center justify-between border-b border-slate-800 pb-5 max-w-4xl mx-auto w-full">
        <button
          onClick={() => {
            stopCamera();
            navigate('/driver');
          }}
          className="flex items-center gap-2 px-3 py-1.5 text-xs font-semibold text-slate-400 hover:text-slate-200 bg-slate-900 border border-slate-800 rounded-xl transition"
        >
          <ArrowLeft className="w-4 h-4" /> Cab Portal
        </button>
        <span className="text-sm font-bold text-slate-300">Driver Facial Authentication</span>
      </header>

      <main className="max-w-2xl mx-auto w-full my-auto py-6">
        {authResult ? (
          <div className="bg-slate-900 border border-cyan-500/40 rounded-3xl p-8 sm:p-10 text-center animate-in fade-in zoom-in-95 duration-300">
            <div className="w-16 h-16 bg-cyan-500/10 text-cyan-400 rounded-2xl flex items-center justify-center mx-auto mb-6 border border-cyan-500/20">
              <CheckCircle2 className="w-10 h-10" />
            </div>

            <span className="text-xs uppercase tracking-widest font-bold text-cyan-400">Driver Verified</span>
            <h2 className="text-3xl font-extrabold text-white mt-1 mb-2">
              Welcome, {authResult.name}
            </h2>
            <p className="text-xs text-slate-400 mb-6">
              Biometric similarity score: {(authResult.similarity * 100).toFixed(1)}% &bull; Driver #{authResult.driver_id}
            </p>

            {/* Vehicle Assignment Card */}
            {authResult.vehicle_id ? (
              <div className="bg-slate-950 border border-slate-800 rounded-2xl p-6 text-left mb-8">
                <div className="flex items-center gap-3 mb-4">
                  <div className="p-2.5 bg-blue-500/10 text-blue-400 rounded-xl border border-blue-500/20">
                    <Truck className="w-6 h-6" />
                  </div>
                  <div>
                    <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Assigned Commercial Vehicle</span>
                    <h4 className="text-lg font-bold text-white">{authResult.vehicle_registration}</h4>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-2 text-xs border-t border-slate-800/80 pt-3">
                  <div>
                    <span className="text-slate-500">Model:</span>{' '}
                    <span className="text-slate-200 font-semibold">{authResult.vehicle_model}</span>
                  </div>
                  <div>
                    <span className="text-slate-500">Type:</span>{' '}
                    <span className="text-slate-200 font-semibold">{authResult.vehicle_type}</span>
                  </div>
                </div>
              </div>
            ) : (
              <div className="bg-amber-500/10 border border-amber-500/30 rounded-2xl p-6 text-left mb-8 flex items-start gap-4">
                <ShieldAlert className="w-6 h-6 text-amber-400 shrink-0 mt-0.5" />
                <div>
                  <h4 className="text-sm font-bold text-amber-400 mb-1">No Vehicle Assigned</h4>
                  <p className="text-xs text-amber-200/80 leading-relaxed">
                    You do not currently have a commercial vehicle assigned to your profile. Please contact the Fleet Safety Manager to assign a vehicle on the Fleet Workspace before beginning trip monitoring.
                  </p>
                </div>
              </div>
            )}

            <div className="flex flex-col sm:flex-row gap-4 justify-center">
              {authResult.vehicle_id ? (
                <button
                  type="button"
                  disabled={startingSession}
                  onClick={handleStartShift}
                  className="px-8 py-4 bg-gradient-to-r from-emerald-500 to-cyan-500 hover:from-emerald-400 hover:to-cyan-400 text-slate-950 font-extrabold text-base rounded-2xl transition shadow-xl shadow-cyan-500/20 flex items-center justify-center gap-2"
                >
                  {startingSession ? (
                    <>
                      <Loader2 className="w-5 h-5 animate-spin" />
                      Initializing Cab Safety Monitoring...
                    </>
                  ) : (
                    'START MONITORING & SHIFT'
                  )}
                </button>
              ) : (
                <button
                  onClick={() => {
                    setAuthResult(null);
                    startCamera();
                  }}
                  className="px-6 py-3 bg-slate-800 hover:bg-slate-700 text-slate-200 font-semibold rounded-xl transition"
                >
                  Try Another Driver
                </button>
              )}

              {authResult.vehicle_id && (
                <button
                  disabled={startingSession}
                  onClick={() => {
                    setAuthResult(null);
                    startCamera();
                  }}
                  className="px-6 py-3 bg-slate-800 hover:bg-slate-700 text-slate-300 font-semibold rounded-2xl transition"
                >
                  Switch Driver
                </button>
              )}
            </div>
          </div>
        ) : (
          <div className="bg-slate-900 border border-slate-800 rounded-3xl p-6 sm:p-8 flex flex-col items-center">
            <div className="w-full flex items-center justify-between mb-4">
              <div>
                <h2 className="text-xl font-bold text-white">Biometric Login</h2>
                <p className="text-xs text-slate-400">Position your face in front of the camera</p>
              </div>
              <button
                type="button"
                onClick={startCamera}
                className="flex items-center gap-1 text-xs text-cyan-400 hover:text-cyan-300 font-semibold"
              >
                <RefreshCw className="w-3.5 h-3.5" /> Restart
              </button>
            </div>

            {/* Camera Viewport */}
            <div className="relative w-full aspect-[4/3] bg-slate-950 rounded-2xl overflow-hidden border border-slate-800 flex items-center justify-center mb-6">
              <video
                ref={videoRef}
                autoPlay
                playsInline
                muted
                className="w-full h-full object-cover transform -scale-x-100"
              />

              {/* Target Focus Ring */}
              <div className="absolute inset-0 pointer-events-none flex items-center justify-center">
                <div className={`w-52 h-64 border-2 rounded-[40%] transition-colors duration-300 ${
                  authenticating ? 'border-cyan-400 bg-cyan-500/10 animate-pulse' : 'border-slate-500/50'
                }`} />
              </div>

              <canvas ref={canvasRef} className="hidden" />
            </div>

            {errorMsg && (
              <div className="w-full mb-6 p-4 bg-rose-500/10 border border-rose-500/30 rounded-2xl flex items-start gap-3 text-xs text-rose-400">
                <AlertCircle className="w-5 h-5 shrink-0" />
                <span>{errorMsg}</span>
              </div>
            )}

            <button
              type="button"
              disabled={!cameraActive || authenticating}
              onClick={handleAuthenticate}
              className="w-full py-4 bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 disabled:opacity-50 text-slate-950 font-extrabold text-base rounded-2xl transition shadow-xl shadow-cyan-500/10 flex items-center justify-center gap-2"
            >
              {authenticating ? (
                <>
                  <Loader2 className="w-5 h-5 animate-spin" />
                  Verifying Biometrics with ArcFace...
                </>
              ) : (
                <>
                  <Camera className="w-5 h-5" />
                  Authenticate & Identify Driver
                </>
              )}
            </button>
          </div>
        )}
      </main>
    </div>
  );
}
