import React from 'react';
import { Link } from 'react-router-dom';
import AlertLevelBadge from '../common/AlertLevelBadge';
import EmptyState from '../common/EmptyState';
import { formatTimeOnly } from '../../utils/formatters';
import { AlertCircle, ArrowRight, MapPin } from 'lucide-react';

export default function RecentAlertsSection({ alerts = [] }) {
  if (!alerts.length) {
    return <EmptyState title="No recent alerts" description="Zero safety infractions recorded today." />;
  }

  return (
    <div className="divide-y divide-slate-100">
      {alerts.map((alert) => (
        <div key={alert.alert_id} className="py-3 flex items-start justify-between gap-3 group">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <AlertLevelBadge level={alert.level} showLabel={false} />
              <span className="font-semibold text-slate-900 text-xs">{alert.driver_name}</span>
              <span className="text-slate-400 text-[11px]">({alert.vehicle_plate})</span>
            </div>
            <p className="text-xs text-slate-700 font-medium">{alert.event_type}</p>
            <div className="flex items-center gap-2 text-[11px] text-slate-400">
              <span className="flex items-center gap-0.5">
                <MapPin className="w-3 h-3" />
                {alert.location}
              </span>
              <span>•</span>
              <span>{formatTimeOnly(alert.timestamp)}</span>
            </div>
          </div>
          <div className="text-right shrink-0">
            <span
              className={`text-[10px] font-semibold px-2 py-0.5 rounded ${
                alert.status === 'FLAGGED'
                  ? 'bg-red-50 text-red-700 border border-red-200'
                  : alert.status === 'ACKNOWLEDGED'
                  ? 'bg-amber-50 text-amber-700 border border-amber-200'
                  : 'bg-slate-100 text-slate-600'
              }`}
            >
              {alert.status}
            </span>
          </div>
        </div>
      ))}
      <div className="pt-3 text-center">
        <Link
          to="/alerts"
          className="inline-flex items-center gap-1 text-xs font-semibold text-blue-600 hover:text-blue-800 transition-colors"
        >
          View Full Alert History <ArrowRight className="w-3 h-3" />
        </Link>
      </div>
    </div>
  );
}
