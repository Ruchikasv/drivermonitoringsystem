import React, { useState } from 'react';
import StatusBadge from '../common/StatusBadge';
import DriverProfileModal from './DriverProfileModal';
import { Database, FlaskConical, Phone, Mail, FileText, Truck, Calendar, UserCheck } from 'lucide-react';
import { formatDate } from '../../utils/formatters';

export default function DriverProfileHeader({ driver, onProfileUpdated }) {
  const [isModalOpen, setIsModalOpen] = useState(false);

  if (!driver) return null;

  const hasProfileInfo = Boolean(driver.phone || driver.email || driver.license_no);
  const regNumber = driver.vehicle ? driver.vehicle.registration_number : driver.vehicle_plate;
  const vehicleModel = driver.vehicle ? driver.vehicle.model : driver.assigned_vehicle;

  return (
    <>
      <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-subtle">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
          {/* Left Side: Avatar & Core Identification */}
          <div className="flex items-start gap-4">
            <div className="w-16 h-16 rounded-2xl bg-slate-900 text-white font-extrabold flex items-center justify-center text-2xl shadow-sm shrink-0">
              {driver.name.charAt(0)}
            </div>
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <h1 className="text-xl font-bold text-slate-900 tracking-tight">{driver.name}</h1>
                <span className="font-mono text-xs font-semibold px-2 py-0.5 rounded bg-slate-100 text-slate-700">
                  ID #{driver.driver_id}
                </span>
                <StatusBadge status={driver.status} />
                {driver.isRegisteredBackend ? (
                  <span className="inline-flex items-center gap-1 text-xs font-bold text-blue-700 bg-blue-50 px-2.5 py-0.5 rounded border border-blue-200">
                    <Database className="w-3.5 h-3.5 text-blue-600" />
                    REAL DATABASE RECORD (SQLite)
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 text-xs font-semibold text-amber-800 bg-amber-50 px-2.5 py-0.5 rounded border border-amber-200">
                    <FlaskConical className="w-3.5 h-3.5 text-amber-600" />
                    DEMO DATA (Simulation)
                  </span>
                )}
              </div>

              {/* Quick Metadata Info */}
              <div className="mt-3 flex items-center gap-4 flex-wrap text-xs text-slate-500">
                <span className="flex items-center gap-1.5">
                  <Phone className="w-3.5 h-3.5 text-slate-400" />
                  {driver.phone ? driver.phone : <span className="text-slate-400 italic">Not provided</span>}
                </span>
                <span className="flex items-center gap-1.5">
                  <Mail className="w-3.5 h-3.5 text-slate-400" />
                  {driver.email ? driver.email : <span className="text-slate-400 italic">Not provided</span>}
                </span>
                <span className="flex items-center gap-1.5">
                  <FileText className="w-3.5 h-3.5 text-slate-400" />
                  DL: {driver.license_no ? <strong className="text-slate-700 font-mono">{driver.license_no}</strong> : <span className="text-slate-400 italic">Not provided</span>}
                </span>
                <span className="flex items-center gap-1.5">
                  <Calendar className="w-3.5 h-3.5 text-slate-400" />
                  Enrolled: {formatDate(driver.created_at)}
                </span>
              </div>
            </div>
          </div>

          {/* Right Side: Assigned Commercial Vehicle Box & Profile Edit Action */}
          <div className="flex flex-col sm:flex-row md:flex-col lg:flex-row items-stretch sm:items-center gap-3">
            <div className="bg-slate-50 border border-slate-200/80 rounded-lg p-3.5 min-w-[200px]">
              <div className="flex items-center gap-2 text-xs font-semibold text-slate-700">
                <Truck className="w-4 h-4 text-blue-600" />
                <span>Assigned Commercial Unit</span>
              </div>
              <div className="mt-1">
                <span className="font-mono font-bold text-sm text-slate-900 block">
                  {regNumber ? regNumber : <span className="text-slate-400 font-sans font-normal italic">Not assigned</span>}
                </span>
                <span className="text-xs text-slate-500 block truncate">
                  {vehicleModel ? vehicleModel : <span className="text-slate-400 italic">Awaiting fleet assignment</span>}
                </span>
              </div>
            </div>

            <button
              onClick={() => setIsModalOpen(true)}
              className="inline-flex items-center justify-center gap-1.5 px-3.5 py-2.5 rounded-lg text-xs font-semibold text-blue-700 bg-blue-50 hover:bg-blue-100 border border-blue-200 transition-colors shrink-0"
            >
              <UserCheck className="w-4 h-4 text-blue-600" />
              <span>{hasProfileInfo ? 'Edit Driver Profile' : 'Complete Profile'}</span>
            </button>
          </div>
        </div>
      </div>

      {/* Edit/Complete Profile Modal */}
      <DriverProfileModal
        driver={driver}
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onSave={async (updatedFields) => {
          if (onProfileUpdated) {
            await onProfileUpdated(updatedFields);
          }
        }}
      />
    </>
  );
}
