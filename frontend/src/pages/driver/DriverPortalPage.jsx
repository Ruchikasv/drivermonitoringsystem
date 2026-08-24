import React from 'react';
import { useNavigate } from 'react-router-dom';
import { ShieldCheck, UserCheck, UserPlus, ArrowLeft, Truck, AlertTriangle } from 'lucide-react';

export default function DriverPortalPage() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col justify-between p-6 sm:p-12 font-sans selection:bg-cyan-500 selection:text-white">
      {/* Top Header */}
      <header className="flex items-center justify-between border-b border-slate-800/80 pb-6">
        <div className="flex items-center gap-3">
          <div className="p-3 bg-cyan-500/10 border border-cyan-500/30 rounded-2xl text-cyan-400">
            <Truck className="w-8 h-8" />
          </div>
          <div>
            <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent">
              Driver Cab Portal
            </h1>
            <p className="text-xs sm:text-sm text-slate-400 font-medium">
              Commercial Vehicle Intelligent Safety & Drowsiness Monitoring
            </p>
          </div>
        </div>

        <button
          onClick={() => navigate('/')}
          className="flex items-center gap-2 px-4 py-2 text-xs font-semibold text-slate-400 hover:text-slate-200 bg-slate-900 border border-slate-800 rounded-xl hover:border-slate-700 transition"
        >
          <ArrowLeft className="w-4 h-4" /> Owner Portal
        </button>
      </header>

      {/* Main Action Workspace */}
      <main className="max-w-4xl mx-auto w-full my-auto py-8">
        <div className="text-center mb-10">
          <span className="px-3 py-1 bg-cyan-500/10 text-cyan-400 text-xs font-bold uppercase tracking-widest rounded-full border border-cyan-500/20">
            Euro NCAP 2026 Compliant
          </span>
          <h2 className="text-3xl sm:text-4xl font-bold mt-4 mb-2 text-white">
            Driver Authentication & Shift Start
          </h2>
          <p className="text-slate-400 text-sm max-w-lg mx-auto">
            Please authenticate using facial recognition before operating your assigned vehicle.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Card 1: Facial Authentication (Primary) */}
          <div
            onClick={() => navigate('/driver/auth')}
            className="group relative cursor-pointer bg-gradient-to-b from-slate-900 to-slate-900/60 border border-slate-800 hover:border-cyan-500/50 rounded-3xl p-8 transition-all duration-300 hover:shadow-2xl hover:shadow-cyan-500/10 hover:-translate-y-1"
          >
            <div className="p-4 bg-cyan-500/10 text-cyan-400 rounded-2xl w-fit mb-6 border border-cyan-500/20 group-hover:scale-110 transition-transform">
              <UserCheck className="w-10 h-10" />
            </div>
            <h3 className="text-2xl font-bold text-white mb-2 group-hover:text-cyan-400 transition">
              Facial Authentication
            </h3>
            <p className="text-slate-400 text-sm mb-6 leading-relaxed">
              Verify your identity instantly using ArcFace biometric recognition and verify your assigned vehicle to start real-time monitoring.
            </p>
            <div className="flex items-center text-xs font-bold text-cyan-400 uppercase tracking-wider group-hover:translate-x-1 transition-transform">
              Start Driver Login &rarr;
            </div>
          </div>

          {/* Card 2: Driver Enrollment */}
          <div
            onClick={() => navigate('/driver/register')}
            className="group relative cursor-pointer bg-gradient-to-b from-slate-900 to-slate-900/60 border border-slate-800 hover:border-blue-500/50 rounded-3xl p-8 transition-all duration-300 hover:shadow-2xl hover:shadow-blue-500/10 hover:-translate-y-1"
          >
            <div className="p-4 bg-blue-500/10 text-blue-400 rounded-2xl w-fit mb-6 border border-blue-500/20 group-hover:scale-110 transition-transform">
              <UserPlus className="w-10 h-10" />
            </div>
            <h3 className="text-2xl font-bold text-white mb-2 group-hover:text-blue-400 transition">
              New Driver Enrollment
            </h3>
            <p className="text-slate-400 text-sm mb-6 leading-relaxed">
              Register a new commercial driver profile and capture high-accuracy face embedding vectors for future shift authentication.
            </p>
            <div className="flex items-center text-xs font-bold text-blue-400 uppercase tracking-wider group-hover:translate-x-1 transition-transform">
              Register New Profile &rarr;
            </div>
          </div>
        </div>
      </main>

      {/* Footer System Status */}
      <footer className="border-t border-slate-800/80 pt-6 flex flex-col sm:flex-row items-center justify-between text-xs text-slate-500 gap-4">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
          <span>Camera & Sensor Gateway Ready</span>
        </div>
        <div>
          Intelligent Fleet Safety DMS &bull; CSE Final Year Project
        </div>
      </footer>
    </div>
  );
}
