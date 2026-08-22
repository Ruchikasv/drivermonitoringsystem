import React from 'react';
import { Link } from 'react-router-dom';
import StatusBadge from '../common/StatusBadge';
import SafetyScore from '../common/SafetyScore';
import EmptyState from '../common/EmptyState';
import { ArrowRight, Database, FlaskConical, Phone, Car, Clock } from 'lucide-react';

export default function DriverListTable({ drivers = [] }) {
  if (!drivers.length) {
    return <EmptyState title="No drivers match your search" description="Try adjusting your filter or search query." />;
  }

  return (
    <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-subtle">
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs border-collapse">
          <thead>
            <tr className="border-b border-slate-200 text-slate-500 bg-slate-50/75">
              <th className="py-3 px-5 font-semibold uppercase tracking-wider">Driver</th>
              <th className="py-3 px-5 font-semibold uppercase tracking-wider">Driver ID</th>
              <th className="py-3 px-5 font-semibold uppercase tracking-wider">Record Type</th>
              <th className="py-3 px-5 font-semibold uppercase tracking-wider">Duty Status</th>
              <th className="py-3 px-5 font-semibold uppercase tracking-wider">Vehicle Assigned</th>
              <th className="py-3 px-5 font-semibold uppercase tracking-wider">Driving Hours</th>
              <th className="py-3 px-5 font-semibold uppercase tracking-wider">Total Trips</th>
              <th className="py-3 px-5 font-semibold uppercase tracking-wider">Safety Score</th>
              <th className="py-3 px-5 font-semibold uppercase tracking-wider text-right">Profile</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {drivers.map((driver) => {
              const regNumber = driver.vehicle ? driver.vehicle.registration_number : driver.vehicle_plate;
              const vehicleModel = driver.vehicle ? driver.vehicle.model : driver.assigned_vehicle;

              return (
                <tr key={driver.driver_id} className="hover:bg-slate-50/80 transition-colors">
                  <td className="py-4 px-5">
                    <div className="flex items-center gap-3">
                      <div className="w-9 h-9 rounded-full bg-slate-900 text-white font-bold flex items-center justify-center text-xs shadow-sm">
                        {driver.name.charAt(0)}
                      </div>
                      <div>
                        <div className="font-bold text-slate-900 text-sm">
                          {driver.name}
                        </div>
                        <span className="text-slate-500 text-xs flex items-center gap-1">
                          <Phone className="w-3 h-3 text-slate-400" />
                          {driver.phone || 'Not provided'}
                        </span>
                      </div>
                    </div>
                  </td>
                  <td className="py-4 px-5 font-mono text-slate-700 font-semibold">#{driver.driver_id}</td>
                  <td className="py-4 px-5">
                    {driver.isRegisteredBackend ? (
                      <span
                        className="inline-flex items-center gap-1 text-[10px] font-bold text-blue-700 bg-blue-50 px-2 py-0.5 rounded border border-blue-200"
                        title="Enrolled in data/drivers.db (SQLite)"
                      >
                        <Database className="w-2.5 h-2.5 text-blue-600" />
                        REAL DB RECORD
                      </span>
                    ) : (
                      <span
                        className="inline-flex items-center gap-1 text-[10px] font-semibold text-amber-800 bg-amber-50 px-2 py-0.5 rounded border border-amber-200"
                        title="Synthetic profile for fleet UI simulation"
                      >
                        <FlaskConical className="w-2.5 h-2.5 text-amber-600" />
                        DEMO DATA
                      </span>
                    )}
                  </td>
                  <td className="py-4 px-5">
                    <StatusBadge status={driver.status} />
                  </td>
                  <td className="py-4 px-5">
                    {regNumber ? (
                      <>
                        <div className="flex items-center gap-1.5 font-medium text-slate-800">
                          <Car className="w-3.5 h-3.5 text-slate-400" />
                          <span>{regNumber}</span>
                        </div>
                        {vehicleModel && (
                          <span className="text-[11px] text-slate-400 block truncate max-w-[140px]">
                            {vehicleModel}
                          </span>
                        )}
                      </>
                    ) : (
                      <span className="text-slate-400 italic">
                        Not assigned
                      </span>
                    )}
                  </td>
                  <td className="py-4 px-5 font-medium text-slate-700">
                    <div className="flex items-center gap-1">
                      <Clock className="w-3.5 h-3.5 text-slate-400" />
                      <span>{driver.driving_hours !== null && driver.driving_hours !== undefined ? `${driver.driving_hours}h` : '—'}</span>
                    </div>
                  </td>
                  <td className="py-4 px-5 font-semibold text-slate-800">
                    {driver.total_trips !== null && driver.total_trips !== undefined ? driver.total_trips : '—'}
                  </td>
                  <td className="py-4 px-5">
                    <SafetyScore score={driver.safety_score} />
                  </td>
                  <td className="py-4 px-5 text-right">
                    <Link
                      to={`/drivers/${driver.driver_id}`}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-100 hover:bg-blue-50 hover:text-blue-700 text-slate-700 transition-colors border border-slate-200"
                    >
                      View Details <ArrowRight className="w-3 h-3" />
                    </Link>
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
