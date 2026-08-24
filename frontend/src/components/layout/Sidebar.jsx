import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  Users,
  Eye,
  Route,
  AlertTriangle,
  BarChart3,
  Settings,
  ShieldCheck,
  Truck,
  Camera,
  ExternalLink,
} from 'lucide-react';

const NAV_ITEMS = [
  { name: 'Dashboard', path: '/', icon: LayoutDashboard },
  { name: 'Drivers', path: '/drivers', icon: Users },
  { name: 'Vehicles', path: '/vehicles', icon: Truck },
  { name: 'Live Surveillance', path: '/live-monitoring', icon: Eye, badge: 'Live' },
  { name: 'Incidents & Evidence', path: '/incidents', icon: Camera },
  { name: 'Trips', path: '/trips', icon: Route },
  { name: 'Analytics', path: '/analytics', icon: BarChart3 },
  { name: 'Settings', path: '/settings', icon: Settings },
];


export default function Sidebar() {
  return (
    <aside className="w-64 bg-slate-900 text-slate-300 flex flex-col shrink-0 min-h-screen border-r border-slate-800">
      {/* Brand Header */}
      <div className="h-16 px-6 flex items-center gap-3 border-b border-slate-800 bg-slate-950/40">
        <div className="p-2 rounded-lg bg-blue-600 text-white shadow-sm">
          <Truck className="w-5 h-5" />
        </div>
        <div>
          <h1 className="text-sm font-bold text-white tracking-wide">FLEET SAFETY</h1>
          <p className="text-[10px] text-blue-400 font-medium tracking-wider uppercase">
            Driver Monitoring System
          </p>
        </div>
      </div>

      {/* Navigation List */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        <div className="px-3 pb-2 text-[10px] font-semibold text-slate-500 uppercase tracking-wider">
          Operations
        </div>
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) =>
                `flex items-center justify-between px-3 py-2.5 rounded-lg text-xs font-medium transition-colors ${
                  isActive
                    ? 'bg-blue-600 text-white shadow-sm font-semibold'
                    : 'text-slate-400 hover:text-slate-100 hover:bg-slate-800/60'
                }`
              }
            >
              <div className="flex items-center gap-3">
                <Icon className="w-4 h-4 shrink-0" />
                <span>{item.name}</span>
              </div>
              {item.badge && (
                <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-blue-900/60 text-blue-300 border border-blue-700/50">
                  {item.badge}
                </span>
              )}
            </NavLink>
          );
        })}
      </nav>

      {/* System Status & Driver Portal Button */}
      <div className="p-4 border-t border-slate-800 bg-slate-950/30 space-y-3">
        <NavLink
          to="/driver"
          className="flex items-center justify-center gap-2 w-full py-2.5 px-3 bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-slate-950 font-bold text-xs rounded-xl shadow-md transition"
        >
          <Truck className="w-4 h-4" /> Driver Cab Portal &rarr;
        </NavLink>

        <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-slate-800/60 border border-slate-700/50">
          <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0" />
          <div className="text-[11px] truncate">
            <span className="font-semibold text-slate-200 block">DMS Engine v2.0</span>
            <span className="text-slate-400 text-[10px]">ArcFace + FatigueLSTM Ready</span>
          </div>
        </div>
      </div>

    </aside>
  );
}
