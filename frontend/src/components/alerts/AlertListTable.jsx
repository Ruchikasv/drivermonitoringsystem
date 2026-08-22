import React from 'react';
import AlertLevelBadge from '../common/AlertLevelBadge';
import EmptyState from '../common/EmptyState';
import { formatDateTime } from '../../utils/formatters';
import { MapPin, CheckCircle, Info } from 'lucide-react';

export default function AlertListTable({ alerts = [] }) {
  if (!alerts.length) {
    return <EmptyState title="No alerts found" description="No alerts match your filter criteria." />;
  }

  return (
    <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-subtle">
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs border-collapse">
          <thead>
            <tr className="border-b border-slate-200 text-slate-500 bg-slate-50/75">
              <th className="py-3 px-5 font-semibold uppercase tracking-wider">Alert ID</th>
              <th className="py-3 px-5 font-semibold uppercase tracking-wider">Severity Level</th>
              <th className="py-3 px-5 font-semibold uppercase tracking-wider">Driver & Unit</th>
              <th className="py-3 px-5 font-semibold uppercase tracking-wider">Infraction Event</th>
              <th className="py-3 px-5 font-semibold uppercase tracking-wider">Time Recorded</th>
              <th className="py-3 px-5 font-semibold uppercase tracking-wider">Location</th>
              <th className="py-3 px-5 font-semibold uppercase tracking-wider">Resolution Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {alerts.map((alert) => (
              <tr key={alert.alert_id} className="hover:bg-slate-50/80 transition-colors">
                <td className="py-4 px-5 font-mono font-bold text-slate-900">
                  {alert.alert_id}
                </td>

                <td className="py-4 px-5">
                  <AlertLevelBadge level={alert.level} />
                </td>

                <td className="py-4 px-5">
                  <div className="font-bold text-slate-900">{alert.driver_name}</div>
                  <span className="text-slate-500 text-[11px] font-mono">{alert.vehicle_plate}</span>
                </td>

                <td className="py-4 px-5">
                  <div className="font-semibold text-slate-800">{alert.event_type}</div>
                  <p className="text-[11px] text-slate-500 mt-0.5 max-w-xs truncate" title={alert.notes}>
                    {alert.notes}
                  </p>
                </td>

                <td className="py-4 px-5 text-slate-600 font-medium whitespace-nowrap">
                  {formatDateTime(alert.timestamp)}
                </td>

                <td className="py-4 px-5 text-slate-600">
                  <div className="flex items-center gap-1">
                    <MapPin className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                    <span className="truncate max-w-[160px]">{alert.location}</span>
                  </div>
                </td>

                <td className="py-4 px-5">
                  <span
                    className={`inline-flex items-center gap-1 px-2.5 py-1 rounded text-xs font-semibold ${
                      alert.status === 'FLAGGED'
                        ? 'bg-red-50 text-red-700 border border-red-200'
                        : alert.status === 'ACKNOWLEDGED'
                        ? 'bg-amber-50 text-amber-700 border border-amber-200'
                        : 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                    }`}
                  >
                    {alert.status === 'RESOLVED' && <CheckCircle className="w-3 h-3" />}
                    {alert.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
