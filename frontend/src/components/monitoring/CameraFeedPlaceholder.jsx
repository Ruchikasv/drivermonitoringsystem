import React from 'react';
import { Camera, AlertCircle, ShieldCheck, VideoOff, RefreshCw } from 'lucide-react';

export default function CameraFeedPlaceholder({
  driverName = 'Ruchika',
  driverId = 1,
  vehiclePlate = 'KA-01-MJ-8821',
  cameraIndex = 0,
}) {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-card">
      {/* Video Feed Header Bar */}
      <div className="bg-slate-950 px-4 py-2.5 flex items-center justify-between border-b border-slate-800 text-xs">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
          <span className="font-semibold text-slate-200">IN-CABIN MONITORING FEED</span>
          <span className="text-slate-500 font-mono text-[11px]">(CAM-{cameraIndex})</span>
        </div>
        <div className="flex items-center gap-3 text-[11px] text-slate-400">
          <span>Target: <strong className="text-slate-200">{driverName} (#{driverId})</strong></span>
          <span>•</span>
          <span className="font-mono text-slate-300">{vehiclePlate}</span>
        </div>
      </div>

      {/* Simulated Video Canvas / Stream Container */}
      <div className="relative aspect-video w-full bg-slate-950 flex flex-col items-center justify-center p-6 text-center">
        {/* Simulated Camera Overlay Corner Brackets */}
        <div className="absolute top-4 left-4 w-6 h-6 border-t-2 border-l-2 border-slate-600" />
        <div className="absolute top-4 right-4 w-6 h-6 border-t-2 border-r-2 border-slate-600" />
        <div className="absolute bottom-4 left-4 w-6 h-6 border-b-2 border-l-2 border-slate-600" />
        <div className="absolute bottom-4 right-4 w-6 h-6 border-b-2 border-r-2 border-slate-600" />

        {/* Center Target Box Frame */}
        <div className="relative border border-dashed border-blue-500/40 rounded-xl p-8 max-w-sm flex flex-col items-center justify-center bg-blue-950/10 backdrop-blur-[2px]">
          <div className="w-14 h-14 rounded-full bg-slate-800/80 border border-slate-700 flex items-center justify-center text-blue-400 mb-3 shadow-inner">
            <Camera className="w-7 h-7" />
          </div>

          <h4 className="text-sm font-semibold text-white">Live Video Feed Placeholder</h4>
          <p className="text-xs text-slate-400 mt-1 max-w-xs">
            Facial recognition authentication initialized in Phase 1. Real-time stream processing pipeline will connect in Phase 2.
          </p>

          <div className="mt-4 px-3 py-1.5 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-300 text-[11px] flex items-center gap-2">
            <AlertCircle className="w-3.5 h-3.5 shrink-0" />
            <span>Awaiting real-time drowsiness CV pipeline</span>
          </div>
        </div>

        {/* Bottom Stream Status Strip */}
        <div className="absolute bottom-3 left-6 right-6 flex items-center justify-between text-[10px] text-slate-500 font-mono">
          <div className="flex items-center gap-3">
            <span>RES: 1280x720</span>
            <span>FPS: 30 (Awaiting Stream)</span>
          </div>
          <div className="flex items-center gap-1.5 text-blue-400">
            <ShieldCheck className="w-3.5 h-3.5" />
            <span>Driver Auth: Active</span>
          </div>
        </div>
      </div>
    </div>
  );
}
