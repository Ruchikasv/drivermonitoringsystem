import React, { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Camera, ArrowLeft, CheckCircle2, AlertCircle, Loader2, RefreshCw } from 'lucide-react';
import { authService } from '../../services/authService';

export default function DriverRegisterPage() {
  const navigate = useNavigate();
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);

  const [formData, setFormData] = useState({
    name: '',
    phone: '',
    email: '',
    license_no: '',
  });

  const [cameraActive, setCameraActive] = useState(false);
  const [capturing, setCapturing] = useState(false);
  const [capturedFrames, setCapturedFrames] = useState([]);
  const [progress, setProgress] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [registrationStatusText, setRegistrationStatusText] = useState('');
  const [successResult, setSuccessResult] = useState(null);
  const [errorMsg, setErrorMsg] = useState(null);

  // Stop camera tracks explicitly
  const stopCamera = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    setCameraActive(false);
  };

  // Start browser camera
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
      console.error('Camera access error:', err);
      setErrorMsg('Could not access webcam. Please allow browser camera permissions.');
      setCameraActive(false);
    }
  };

  useEffect(() => {
    startCamera();
    return () => {
      stopCamera();
    };
  }, []);

  // Capture 10 frames sequentially
  const handleCaptureSamples = async () => {
    if (!formData.name.trim()) {
      setErrorMsg('Please enter the driver full name first.');
      return;
    }
    if (!videoRef.current || !canvasRef.current || capturing || submitting) return;

    setErrorMsg(null);
    setCapturing(true);
    setCapturedFrames([]);
    setProgress(0);

    const frames = [];
    const totalFrames = 10;
    const canvas = canvasRef.current;
    const video = videoRef.current;

    for (let i = 0; i < totalFrames; i++) {
      await new Promise((resolve) => setTimeout(resolve, 180));
      if (!videoRef.current) break;

      canvas.width = video.videoWidth || 640;
      canvas.height = video.videoHeight || 480;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

      const b64 = canvas.toDataURL('image/jpeg', 0.85);
      frames.push(b64);
      setProgress(Math.round(((i + 1) / totalFrames) * 100));
    }

    setCapturedFrames(frames);
    setCapturing(false);

    // Auto submit once captured
    await submitEnrollment(frames);
  };

  const submitEnrollment = async (frames) => {
    setSubmitting(true);
    setErrorMsg(null);
    setRegistrationStatusText('Preparing face recognition...');

    // Dynamic progressive states while waiting for backend
    const timer1 = setTimeout(() => {
      setRegistrationStatusText('Processing face...');
    }, 500);

    const timer2 = setTimeout(() => {
      setRegistrationStatusText('Saving driver registration...');
    }, 1800);

    try {
      const res = await authService.registerDriver({
        name: formData.name.trim(),
        phone: formData.phone.trim() || null,
        email: formData.email.trim() || null,
        license_no: formData.license_no.trim() || null,
        frames_b64: frames,
      });

      clearTimeout(timer1);
      clearTimeout(timer2);
      setRegistrationStatusText('Face registered successfully.');

      // Stop camera immediately once registered successfully
      stopCamera();
      setSuccessResult(res);
    } catch (err) {
      clearTimeout(timer1);
      clearTimeout(timer2);
      console.error('Registration failed:', err);
      const detail =
        err.response?.data?.detail ||
        (err.code === 'ECONNABORTED'
          ? 'Registration timed out. The server may still be processing your biometrics.'
          : err.message || 'Registration failed. Ensure face is clearly visible.');
      setErrorMsg(detail);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col p-6 sm:p-10 font-sans">
      <header className="flex items-center justify-between border-b border-slate-800 pb-5 max-w-5xl mx-auto w-full">
        <button
          onClick={() => {
            stopCamera();
            navigate('/driver');
          }}
          className="flex items-center gap-2 px-3 py-1.5 text-xs font-semibold text-slate-400 hover:text-slate-200 bg-slate-900 border border-slate-800 rounded-xl transition"
        >
          <ArrowLeft className="w-4 h-4" /> Back to Cab Portal
        </button>
        <span className="text-sm font-bold text-slate-300">Driver Facial Enrollment</span>
      </header>

      <main className="max-w-5xl mx-auto w-full my-auto py-8">
        {successResult ? (
          <div className="bg-slate-900 border border-emerald-500/30 rounded-3xl p-8 sm:p-12 max-w-xl mx-auto text-center animate-in fade-in zoom-in-95 duration-300">
            <div className="w-16 h-16 bg-emerald-500/10 text-emerald-400 rounded-2xl flex items-center justify-center mx-auto mb-6 border border-emerald-500/20">
              <CheckCircle2 className="w-10 h-10" />
            </div>
            <h2 className="text-3xl font-bold text-white mb-2">Enrollment Successful!</h2>
            <p className="text-emerald-400 font-semibold text-sm mb-1">
              Face registered successfully.
            </p>
            <p className="text-slate-400 text-sm mb-6">
              Driver profile for <strong className="text-white">{successResult.name}</strong> has been registered with ArcFace biometric vectors.
            </p>
            <div className="bg-slate-950 border border-slate-800 rounded-2xl p-4 mb-8 text-left text-sm space-y-2">
              <div className="flex justify-between">
                <span className="text-slate-500">Assigned Driver ID:</span>
                <span className="font-mono font-bold text-cyan-400">#{successResult.driver_id}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Status:</span>
                <span className="font-semibold text-emerald-400">Biometrics Persisted in Database</span>
              </div>
            </div>
            <div className="flex flex-col sm:flex-row gap-4 justify-center">
              <button
                onClick={() => {
                  stopCamera();
                  navigate('/driver/auth');
                }}
                className="px-6 py-3 bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold rounded-xl transition shadow-lg shadow-cyan-500/20"
              >
                Proceed to Driver Login &rarr;
              </button>
              <button
                onClick={() => {
                  setSuccessResult(null);
                  setFormData({ name: '', phone: '', email: '', license_no: '' });
                  setRegistrationStatusText('');
                  startCamera();
                }}
                className="px-6 py-3 bg-slate-800 hover:bg-slate-700 text-slate-200 font-semibold rounded-xl transition"
              >
                Register Another Driver
              </button>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
            {/* Left Column: Form Details */}
            <div className="lg:col-span-5 bg-slate-900/90 border border-slate-800 rounded-3xl p-6 sm:p-8">
              <h2 className="text-xl font-bold text-white mb-1">Driver Information</h2>
              <p className="text-xs text-slate-400 mb-6">Enter commercial license & contact info</p>

              <div className="space-y-4 text-sm">
                <div>
                  <label className="block text-xs font-semibold text-slate-400 mb-1">Full Name *</label>
                  <input
                    type="text"
                    required
                    disabled={capturing || submitting}
                    placeholder="e.g. Ruchika Sharma"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2.5 text-white placeholder-slate-600 focus:outline-none focus:border-cyan-500 disabled:opacity-60 transition"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-400 mb-1">Driving License Number</label>
                  <input
                    type="text"
                    disabled={capturing || submitting}
                    placeholder="e.g. DL-KA01202200981"
                    value={formData.license_no}
                    onChange={(e) => setFormData({ ...formData, license_no: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2.5 text-white placeholder-slate-600 focus:outline-none focus:border-cyan-500 disabled:opacity-60 transition"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-400 mb-1">Phone Number</label>
                  <input
                    type="text"
                    disabled={capturing || submitting}
                    placeholder="e.g. +91 98765 43210"
                    value={formData.phone}
                    onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2.5 text-white placeholder-slate-600 focus:outline-none focus:border-cyan-500 disabled:opacity-60 transition"
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-400 mb-1">Email Address</label>
                  <input
                    type="email"
                    disabled={capturing || submitting}
                    placeholder="e.g. driver@fleet.com"
                    value={formData.email}
                    onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-2.5 text-white placeholder-slate-600 focus:outline-none focus:border-cyan-500 disabled:opacity-60 transition"
                  />
                </div>
              </div>

              {errorMsg && (
                <div className="mt-6 p-4 bg-rose-500/10 border border-rose-500/30 rounded-2xl flex items-start gap-3 text-xs text-rose-400">
                  <AlertCircle className="w-5 h-5 shrink-0" />
                  <span>{errorMsg}</span>
                </div>
              )}
            </div>

            {/* Right Column: Camera & Biometric Capture */}
            <div className="lg:col-span-7 bg-slate-900/90 border border-slate-800 rounded-3xl p-6 sm:p-8 flex flex-col items-center">
              <div className="w-full flex items-center justify-between mb-4">
                <h2 className="text-xl font-bold text-white">Biometric Face Capture</h2>
                <button
                  type="button"
                  disabled={capturing || submitting}
                  onClick={startCamera}
                  className="flex items-center gap-1.5 text-xs text-cyan-400 hover:text-cyan-300 disabled:opacity-50 font-semibold"
                >
                  <RefreshCw className="w-3.5 h-3.5" /> Reset Camera
                </button>
              </div>

              {/* Video container with face alignment guide */}
              <div className="relative w-full aspect-[4/3] bg-slate-950 rounded-2xl overflow-hidden border border-slate-800 flex items-center justify-center">
                <video
                  ref={videoRef}
                  autoPlay
                  playsInline
                  muted
                  className="w-full h-full object-cover transform -scale-x-100"
                />

                {/* Face Oval Overlay Guide */}
                <div className="absolute inset-0 pointer-events-none flex items-center justify-center">
                  <div className={`w-56 h-72 border-2 border-dashed rounded-[50%] transition-colors duration-300 ${
                    capturing || submitting ? 'border-cyan-400 bg-cyan-500/10 animate-pulse' : 'border-slate-500/60'
                  }`} />
                </div>

                {/* Hidden canvas for snapshot rendering */}
                <canvas ref={canvasRef} className="hidden" />

                {capturing && (
                  <div className="absolute bottom-4 left-4 right-4 bg-slate-950/90 backdrop-blur border border-cyan-500/30 rounded-xl p-3">
                    <div className="flex justify-between text-xs font-semibold text-cyan-400 mb-1.5">
                      <span>Capturing Biometric Vectors...</span>
                      <span>{progress}%</span>
                    </div>
                    <div className="w-full h-2 bg-slate-800 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-cyan-500 transition-all duration-150"
                        style={{ width: `${progress}%` }}
                      />
                    </div>
                  </div>
                )}

                {submitting && (
                  <div className="absolute bottom-4 left-4 right-4 bg-slate-950/90 backdrop-blur border border-cyan-500/30 rounded-xl p-3 flex items-center gap-3">
                    <Loader2 className="w-5 h-5 animate-spin text-cyan-400 shrink-0" />
                    <div className="text-xs font-semibold text-cyan-300">
                      {registrationStatusText || 'Processing face...'}
                    </div>
                  </div>
                )}
              </div>

              <p className="text-xs text-slate-400 mt-4 text-center">
                Position face inside the oval guide and look straight at the camera.
              </p>

              <button
                type="button"
                disabled={!cameraActive || capturing || submitting || !formData.name.trim()}
                onClick={handleCaptureSamples}
                className="mt-6 w-full max-w-sm py-3.5 bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-slate-950 font-bold rounded-2xl transition shadow-xl shadow-cyan-500/10 flex items-center justify-center gap-2"
              >
                {submitting ? (
                  <>
                    <Loader2 className="w-5 h-5 animate-spin" />
                    <span>{registrationStatusText || 'Processing face...'}</span>
                  </>
                ) : capturing ? (
                  <>
                    <Loader2 className="w-5 h-5 animate-spin" />
                    Capturing Samples ({progress}%)...
                  </>
                ) : (
                  <>
                    <Camera className="w-5 h-5" />
                    Capture Face & Complete Enrollment
                  </>
                )}
              </button>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
