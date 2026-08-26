import React from 'react';
import { formatDateTime, formatDuration } from '../../utils/formatters';
import EmptyState from '../common/EmptyState';
import { Route, Clock, CheckCircle2, AlertTriangle } from 'lucide-react';

export default function TripHistoryTable({ trips = [] }) {
  if (!trips.length) {
    return <EmptyState title="No trips found" description="No commercial trip logs recorded." />;
  }

  return (
    <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-subtle">
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs border-collapse">
          <thead>
            <tr className="border-b border-slate-200 text-slate-500 bg-slate-50/75">
              <th className="py-3 px-5 font-semibold uppercase tracking-wider">Trip ID</th>
              <th className="py-3 px-5 font-semibold uppercase tracking-wider">Driver & Unit</th>
              <th className="py-3 px-5 font-semibold uppercase tracking-wider">Route Segments</th>
              <th className="py-3 px-5 font-semibold uppercase tracking-wider">Departure / Arrival</th>
              <th className="py-3 px-5 font-semibold uppercase tracking-wider">Duration</th>
              <th className="py-3 px-5 font-semibold uppercase tracking-wider">Safety Incidents</th>
              <th className="py-3 px-5 font-semibold uppercase tracking-wider">Peak Drowsiness</th>
              <th className="py-3 px-5 font-semibold uppercase tracking-wider">Alcohol Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {trips.map((trip) => {
              const isRunning = trip.status === 'RUNNING' || trip.status === 'IN_PROGRESS';
              const isPaused = trip.status === 'PAUSED';
              return (
                <tr key={trip.trip_id} className="hover:bg-slate-50/80 transition-colors">
                  <td className="py-4 px-5">
                    <span className="font-mono font-bold text-slate-900 text-xs">
                      {trip.trip_id}
                    </span>
                    <span
                      className={`block text-[10px] font-semibold mt-0.5 ${
                        isRunning
                          ? 'text-blue-600 animate-pulse'
                          : isPaused
                          ? 'text-amber-600 font-bold'
                          : 'text-slate-400'
                      }`}
                    >
                      {isRunning ? '● IN ROUTE' : isPaused ? '⏸ PAUSED' : 'COMPLETED'}
                    </span>
                  </td>

                  <td className="py-4 px-5">
                    <div className="font-bold text-slate-900">{trip.driver_name}</div>
                    <span className="text-slate-500 text-[11px] font-mono">{trip.vehicle_plate}</span>
                  </td>

                  <td className="py-4 px-5">
                    <div className="flex items-center gap-1.5 font-medium text-slate-800">
                      <Route className="w-3.5 h-3.5 text-blue-600 shrink-0" />
                      <span>{trip.origin} ➔ {trip.destination}</span>
                    </div>
                  </td>

                  <td className="py-4 px-5 text-slate-600">
                    <div className="space-y-0.5">
                      <div>Dep: {formatDateTime(trip.start_time)}</div>
                      <div className="text-slate-400">
                        Arr: {trip.end_time ? formatDateTime(trip.end_time) : isPaused ? 'Paused' : 'En route'}
                      </div>
                    </div>
                  </td>

                  <td className="py-4 px-5 font-medium text-slate-700">
                    <div className="flex items-center gap-1 font-semibold text-slate-800">
                      <Clock className="w-3.5 h-3.5 text-slate-400" />
                      {formatDuration(trip.active_duration_minutes !== undefined ? trip.active_duration_minutes : trip.duration_minutes)} active
                    </div>
                    {trip.total_paused_minutes > 0 ? (
                      <div className="text-[10px] text-amber-600 font-medium mt-0.5">
                        Paused: {formatDuration(trip.total_paused_minutes)} (Total: {formatDuration(trip.duration_minutes)})
                      </div>
                    ) : (
                      <div className="text-[10px] text-slate-400 font-normal mt-0.5">
                        Total: {formatDuration(trip.duration_minutes)}
                      </div>
                    )}
                  </td>

                  <td className="py-4 px-5">
                    {trip.alerts_count > 0 ? (
                      <span className="inline-flex items-center gap-1 font-semibold text-amber-700 bg-amber-50 px-2 py-0.5 rounded border border-amber-200 text-[11px]">
                        <AlertTriangle className="w-3 h-3" />
                        {trip.alerts_count} Alerts
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200 text-[11px]">
                        <CheckCircle2 className="w-3 h-3" />
                        Zero Alerts
                      </span>
                    )}
                  </td>

                  <td className="py-4 px-5 font-mono text-slate-700 text-xs">
                    {trip.max_drowsiness_score}
                  </td>

                  <td className="py-4 px-5">
                    <span className="inline-flex items-center gap-1 text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded text-[11px] font-semibold border border-emerald-200">
                      <CheckCircle2 className="w-3 h-3" />
                      {trip.alcohol_status}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
