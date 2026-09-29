import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Bell,
  AlertTriangle,
  Flame,
  Info,
  Clock,
  Car,
  User,
  ExternalLink,
  RefreshCw,
  CheckCircle2,
} from 'lucide-react';
import { alertService } from '../../services/alertService';
import { useAuth } from '../../context/AuthContext';

export default function NotificationDropdown() {
  const { owner } = useAuth();
  const navigate = useNavigate();

  const [isOpen, setIsOpen] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [loading, setLoading] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const [hasNewCritical, setHasNewCritical] = useState(false);
  const [lastViewedTimestamp, setLastViewedTimestamp] = useState(null);

  const dropdownRef = useRef(null);

  // Fetch recent safety alerts belonging exclusively to the authenticated owner
  const fetchNotifications = useCallback(async (isManual = false) => {
    if (!owner?.owner_id && !owner?.id) return;
    if (isManual) setLoading(true);

    try {
      const data = await alertService.getRecentAlerts(15);
      const alerts = Array.isArray(data) ? data : [];
      setNotifications(alerts);

      // Determine unread count based on last viewed timestamp
      if (lastViewedTimestamp) {
        const unread = alerts.filter(
          (a) => new Date(a.timestamp).getTime() > lastViewedTimestamp
        ).length;
        setUnreadCount(unread);
      } else {
        setUnreadCount(alerts.length);
      }

      // Check if there are any critical severity alerts
      const criticalExists = alerts.some(
        (a) => a.level === 3 || String(a.event_type).toLowerCase().includes('critical')
      );
      setHasNewCritical(criticalExists);
    } catch (err) {
      console.warn('[NotificationDropdown] Failed to fetch alerts:', err?.message || err);
      // Fallback gracefully without crashing UI
      setNotifications([]);
    } finally {
      if (isManual) setLoading(false);
    }
  }, [owner, lastViewedTimestamp]);

  // Initial fetch and 6-second polling for live safety alert synchronization
  useEffect(() => {
    fetchNotifications();
    const interval = setInterval(() => {
      fetchNotifications();
    }, 6000);

    return () => clearInterval(interval);
  }, [fetchNotifications]);

  // Handle click outside to close dropdown
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  const handleToggleOpen = () => {
    const nextState = !isOpen;
    setIsOpen(nextState);
    if (nextState) {
      // Mark as viewed: reset unread badge count and record timestamp
      setLastViewedTimestamp(Date.now());
      setUnreadCount(0);
      fetchNotifications(true);
    }
  };

  const handleNotificationClick = (alert) => {
    setIsOpen(false);
    if (alert?.driver_name) {
      navigate(`/alerts?search=${encodeURIComponent(alert.driver_name)}`);
    } else {
      navigate('/alerts');
    }
  };

  const formatTime = (ts) => {
    if (!ts) return 'Recent';
    try {
      const date = new Date(ts);
      if (isNaN(date.getTime())) return String(ts);
      const now = new Date();
      const diffMs = now - date;
      const diffMins = Math.floor(diffMs / 60000);
      const diffHours = Math.floor(diffMins / 60);

      if (diffMins < 1) return 'Just now';
      if (diffMins < 60) return `${diffMins}m ago`;
      if (diffHours < 24) return `${diffHours}h ago`;
      return date.toLocaleDateString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
    } catch {
      return String(ts);
    }
  };

  return (
    <div className="relative" ref={dropdownRef}>
      {/* Bell Trigger Button */}
      <button
        type="button"
        onClick={handleToggleOpen}
        className={`p-2 rounded-xl transition-all relative ${
          isOpen
            ? 'bg-blue-50 text-blue-600 ring-2 ring-blue-500/20'
            : 'text-slate-500 hover:text-slate-800 hover:bg-slate-100'
        }`}
        title="Fleet Safety Notifications"
        aria-label="Fleet Safety Notifications"
        aria-expanded={isOpen}
      >
        <Bell className={`w-5 h-5 ${hasNewCritical && unreadCount > 0 ? 'text-rose-600 animate-bounce' : ''}`} />

        {/* Badge Indicator */}
        {unreadCount > 0 && (
          <span
            className={`absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] px-1 rounded-full text-[10px] font-extrabold flex items-center justify-center text-white ring-2 ring-white shadow-sm ${
              hasNewCritical ? 'bg-rose-600 animate-pulse' : 'bg-blue-600'
            }`}
          >
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {/* Notification Dropdown Panel */}
      {isOpen && (
        <div className="absolute right-0 top-full mt-2.5 w-80 sm:w-96 bg-white border border-slate-200/90 rounded-2xl shadow-2xl z-50 overflow-hidden animate-in fade-in slide-in-from-top-2 duration-150">
          {/* Header */}
          <div className="px-4 py-3 bg-slate-50/90 border-b border-slate-200/80 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-slate-900 tracking-tight">
                Safety Alerts & Notifications
              </span>
              <span className="text-[10px] font-semibold px-2 py-0.5 bg-slate-200 text-slate-700 rounded-full font-mono">
                {notifications.length}
              </span>
            </div>
            <button
              onClick={(e) => {
                e.stopPropagation();
                fetchNotifications(true);
              }}
              disabled={loading}
              title="Refresh notifications"
              className="p-1 text-slate-400 hover:text-slate-700 hover:bg-slate-200/60 rounded-md transition"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-blue-600' : ''}`} />
            </button>
          </div>

          {/* Alert Items List */}
          <div className="max-h-[380px] overflow-y-auto divide-y divide-slate-100">
            {notifications.length === 0 ? (
              <div className="py-10 px-4 text-center">
                <div className="w-10 h-10 rounded-full bg-emerald-50 text-emerald-600 mx-auto flex items-center justify-center mb-2.5">
                  <CheckCircle2 className="w-5 h-5" />
                </div>
                <p className="text-xs font-bold text-slate-800">No new notifications</p>
                <p className="text-[11px] text-slate-400 mt-0.5">
                  All active commercial drivers are operating within normal safety limits.
                </p>
              </div>
            ) : (
              notifications.map((alert) => {
                const isCritical = alert.level === 3 || String(alert.event_type).toLowerCase().includes('critical');
                const isWarning = alert.level === 2 || String(alert.event_type).toLowerCase().includes('warning');

                let badgeColor = 'bg-blue-100 text-blue-700 border-blue-200';
                let IconComponent = Info;
                let levelLabel = 'Level 1 Nudge';

                if (isCritical) {
                  badgeColor = 'bg-rose-100 text-rose-700 border-rose-200';
                  IconComponent = Flame;
                  levelLabel = 'Level 3 Critical';
                } else if (isWarning) {
                  badgeColor = 'bg-amber-100 text-amber-800 border-amber-200';
                  IconComponent = AlertTriangle;
                  levelLabel = 'Level 2 Warning';
                }

                return (
                  <div
                    key={alert.alert_id || alert.incident_id}
                    onClick={() => handleNotificationClick(alert)}
                    className={`p-3.5 transition-colors cursor-pointer text-left flex gap-3 items-start ${
                      isCritical
                        ? 'bg-rose-50/40 hover:bg-rose-50/80 border-l-4 border-l-rose-500'
                        : isWarning
                        ? 'hover:bg-amber-50/40 border-l-4 border-l-amber-400'
                        : 'hover:bg-slate-50 border-l-4 border-l-blue-400'
                    }`}
                  >
                    <div className={`p-2 rounded-xl shrink-0 mt-0.5 ${
                      isCritical ? 'bg-rose-100 text-rose-600' : isWarning ? 'bg-amber-100 text-amber-600' : 'bg-blue-100 text-blue-600'
                    }`}>
                      <IconComponent className="w-4 h-4" />
                    </div>

                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-1.5 mb-1">
                        <span className={`text-[10px] font-extrabold uppercase tracking-wider px-2 py-0.5 rounded-md border ${badgeColor}`}>
                          {levelLabel}
                        </span>
                        <span className="text-[10px] text-slate-400 flex items-center gap-1 shrink-0 font-mono">
                          <Clock className="w-2.5 h-2.5" />
                          {formatTime(alert.timestamp)}
                        </span>
                      </div>

                      <div className="flex items-center gap-2 text-xs font-bold text-slate-900 truncate">
                        <span className="flex items-center gap-1">
                          <User className="w-3 h-3 text-slate-400" />
                          {alert.driver_name || 'Driver'}
                        </span>
                        <span className="text-slate-300">&bull;</span>
                        <span className="flex items-center gap-1 font-mono text-[11px] text-slate-600 font-normal">
                          <Car className="w-3 h-3 text-slate-400" />
                          {alert.vehicle_plate || 'Unassigned'}
                        </span>
                      </div>

                      {alert.notes && (
                        <p className="text-[11px] text-slate-500 mt-1 line-clamp-2 leading-relaxed">
                          {alert.notes}
                        </p>
                      )}
                    </div>
                  </div>
                );
              })
            )}
          </div>

          {/* Footer */}
          <div className="p-2.5 bg-slate-50/90 border-t border-slate-200/80 text-center">
            <button
              onClick={() => {
                setIsOpen(false);
                navigate('/alerts');
              }}
              className="w-full py-1.5 px-3 text-xs font-bold text-blue-600 hover:text-blue-700 hover:bg-blue-50/60 rounded-xl transition flex items-center justify-center gap-1.5"
            >
              <span>View All Fleet Alerts Console</span>
              <ExternalLink className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
