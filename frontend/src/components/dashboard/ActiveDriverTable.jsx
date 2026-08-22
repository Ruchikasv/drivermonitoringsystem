import React from 'react';
import { Link } from 'react-router-dom';
import StatusBadge from '../common/StatusBadge';
import SafetyScore from '../common/SafetyScore';
import EmptyState from '../common/EmptyState';
import { ArrowRight, CheckCircle2, AlertTriangle, ShieldCheck, Database, FlaskConical } from 'lucide-react';

export default function ActiveDriverTable({ drivers = [] }) {
  if (!drivers.length) {
    return <EmptyState title="No active drivers" description="All registered drivers are currently off duty." />;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-xs border-collapse">
        <thead>
          <tr className="border-b border-slate-200 text-slate-500 bg-slate-50/75">
            <th className="py-3 px-4 font-semibold uppercase tracking-wider">Driver</th>
            <th className="py-3 px-4 font-semibold uppercase tracking-wider">Driver ID</th>
            <th className="py-3 px-4 font-semibold uppercase tracking-wider">Data Source</th>
            <th className="py-3 px-4 font-semibold uppercase tracking-wider">Status</th>
            <th className="py-3 px-4 font-semibold uppercase tracking-wider">Drowsiness State</th>
            <th className="py-3 px-4 font-semibold uppercase tracking-wider">Alcohol Status</th>
            <th className="py-3 px-4 font-semibold uppercase tracking-wider">Safety Score</th>
            <th className="py-3 px-4 font-semibold uppercase tracking-wider text-right">Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {drivers.map((driver) => {
            const hasAttention = driver.current_trip?.drowsiness_status === 'ATTENTION_NEEDED';
            return (
              <tr key={driver.driver_id} className="hover:bg-slate-50/80 transition-colors">
                <td className="py-3.5 px-4">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full bg-slate-100 border border-slate-200 text-slate-700 font-bold flex items-center justify-center text-xs">
                      {driver.name.charAt(0)}
                    </div>
                    <div>
                      <div className="font-semibold text-slate-900 flex items-center gap-1.5">
                        {driver.name}
                      </div>
                      <span className="text-slate-500 text-[11px]">{driver.vehicle_plate}</span>
                    </div>
                  </div>
                </td>
                <td className="py-3.5 px-4 font-mono text-slate-700">#{driver.driver_id}</td>
                <td className="py-3.5 px-4">
                  {driver.isRegisteredBackend ? (
                    <span
                      className="inline-flex items-center gap-1 text-[10px] font-bold text-blue-700 bg-blue-50 px-2 py-0.5 rounded border border-blue-200"
                      title="Verified enrolled record in data/drivers.db (SQLite)"
                    >
                      <Database className="w-2.5 h-2.5 text-blue-600" />
                      REAL DB RECORD
                    </span>
                  ) : (
                    <span
                      className="inline-flex items-center gap-1 text-[10px] font-semibold text-amber-800 bg-amber-50 px-2 py-0.5 rounded border border-amber-200"
                      title="Mock entity for UI preview"
                    >
                      <FlaskConical className="w-2.5 h-2.5 text-amber-600" />
                      DEMO DATA
                    </span>
                  )}
                </td>
                <td className="py-3.5 px-4">
                  <StatusBadge status={driver.status} />
                </td>
                <td className="py-3.5 px-4">
                  {driver.isRegisteredBackend ? (
                    <span className="text-slate-500 text-[11px] italic">
                      Awaiting CV Stream
                    </span>
                  ) : hasAttention ? (
                    <span className="inline-flex items-center gap-1 text-amber-700 bg-amber-50 px-2 py-0.5 rounded text-[11px] font-medium border border-amber-200">
                      <AlertTriangle className="w-3 h-3" />
                      Attention (Demo)
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded text-[11px] font-medium border border-emerald-200">
                      <CheckCircle2 className="w-3 h-3" />
                      Normal (Demo)
                    </span>
                  )}
                </td>
                <td className="py-3.5 px-4">
                  {driver.isRegisteredBackend ? (
                    <span className="text-slate-500 text-[11px] italic">
                      Sensor Standby
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded text-[11px] font-medium border border-emerald-200">
                      <CheckCircle2 className="w-3 h-3" />
                      Cleared (Demo)
                    </span>
                  )}
                </td>
                <td className="py-3.5 px-4">
                  <SafetyScore score={driver.safety_score} size="sm" />
                </td>
                <td className="py-3.5 px-4 text-right">
                  <Link
                    to={`/drivers/${driver.driver_id}`}
                    className="inline-flex items-center gap-1 text-xs font-semibold text-blue-600 hover:text-blue-800 transition-colors"
                  >
                    Details <ArrowRight className="w-3 h-3" />
                  </Link>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
