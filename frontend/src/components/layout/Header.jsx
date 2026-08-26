import React, { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Search, Bell, Shield, User, LogOut } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';

const PAGE_TITLES = {
  '/': { title: 'Fleet Overview', subtitle: 'Real-time driver activity, fatigue trends & alert tracking' },
  '/dashboard': { title: 'Fleet Overview', subtitle: 'Real-time driver activity, fatigue trends & alert tracking' },
  '/drivers': { title: 'Driver Management', subtitle: 'Registered commercial driver directory & performance scores' },
  '/live-monitoring': { title: 'Live Vehicle Stream', subtitle: 'Computer vision telemetry & in-cabin sensor monitoring' },
  '/trips': { title: 'Trip History Logs', subtitle: 'Commercial transport routes, durations, and safety logs' },
  '/alerts': { title: 'Safety Alert Console', subtitle: 'Multi-level severity alerts and corrective action events' },
  '/analytics': { title: 'Safety & Risk Analytics', subtitle: 'Fleet safety score distribution and fatigue analytics' },
  '/settings': { title: 'System Configuration', subtitle: 'Facial recognition parameters, camera sources & fleet policies' },
};

export default function Header() {
  const location = useLocation();
  const navigate = useNavigate();
  const { owner, logout } = useAuth();

  const currentPath = location.pathname.startsWith('/drivers/') && location.pathname !== '/drivers'
    ? '/drivers'
    : location.pathname;

  const pageInfo = PAGE_TITLES[currentPath] || {
    title: 'Fleet Safety Management',
    subtitle: 'Commercial Vehicle Driver Monitoring System',
  };

  const handleLogout = async () => {
    await logout();
    navigate('/owner/login');
  };

  const initials = owner?.name
    ? owner.name
        .split(' ')
        .map((n) => n[0])
        .slice(0, 2)
        .join('')
        .toUpperCase()
    : 'FM';

  const [searchQuery, setSearchQuery] = useState('');

  const handleSearchKeyDown = (e) => {
    if (e.key === 'Enter' && searchQuery.trim()) {
      navigate(`/drivers?search=${encodeURIComponent(searchQuery.trim())}`);
    }
  };

  return (
    <header className="h-16 bg-white border-b border-slate-200 px-8 flex items-center justify-between shrink-0">
      {/* Page Title & Breadcrumb */}
      <div>
        <h2 className="text-lg font-bold text-slate-900 tracking-tight">{pageInfo.title}</h2>
        <p className="text-xs text-slate-500 hidden md:block">{pageInfo.subtitle}</p>
      </div>

      {/* Action Controls & Manager Profile */}
      <div className="flex items-center gap-4">
        {/* Search Bar */}
        <div className="relative hidden sm:block">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={handleSearchKeyDown}
            placeholder="Search driver, vehicle or trip…"
            className="w-64 pl-9 pr-4 py-1.5 text-xs rounded-lg border border-slate-200 bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-colors"
          />
        </div>

        {/* Notification Bell */}
        <div className="relative">
          <button
            type="button"
            className="p-2 rounded-lg text-slate-500 hover:text-slate-700 hover:bg-slate-100 transition-colors relative"
            title="Active Notifications"
          >
            <Bell className="w-4 h-4" />
            <span className="w-2 h-2 rounded-full bg-red-500 absolute top-1.5 right-1.5 ring-2 ring-white" />
          </button>
        </div>

        {/* Vertical Divider */}
        <div className="h-6 w-px bg-slate-200" />

        {/* Fleet Manager Profile & Logout */}
        <div className="flex items-center gap-3 pl-1">
          <div className="w-8 h-8 rounded-full bg-indigo-600 text-white flex items-center justify-center text-xs font-semibold shadow-sm">
            {initials}
          </div>
          <div className="hidden lg:block text-left">
            <span className="text-xs font-semibold text-slate-800 block leading-tight">
              {owner?.name || 'Fleet Manager'}
            </span>
            <span className="text-[10px] text-slate-500 flex items-center gap-1">
              <Shield className="w-2.5 h-2.5 text-indigo-600" />
              {owner?.email || 'Safety Operations'}
            </span>
          </div>

          <button
            onClick={handleLogout}
            title="Sign Out"
            className="p-2 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition-colors ml-1"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </div>
    </header>
  );
}

