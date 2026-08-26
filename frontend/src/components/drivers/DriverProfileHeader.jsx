import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import StatusBadge from '../common/StatusBadge';
import DriverProfileModal from './DriverProfileModal';
import { Database, FlaskConical, Phone, Mail, FileText, Truck, Calendar, UserCheck, UserX, AlertTriangle } from 'lucide-react';
import { formatDate } from '../../utils/formatters';
import { driverService } from '../../services/driverService';

export default function DriverProfileHeader({ driver, onProfileUpdated }) {
  const navigate = useNavigate();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isFireModalOpen, setIsFireModalOpen] = useState(false);
  const [firing, setFiring] = useState(false);

  if (!driver) return null;

  const hasProfileInfo = Boolean(driver.phone || driver.email || driver.license_no);
  const regNumber = driver.vehicle ? driver.vehicle.registration_number : driver.vehicle_plate;
  const vehicleModel = driver.vehicle ? driver.vehicle.model : driver.assigned_vehicle;

  const handleConfirmFire = async () => {
    try {
      setFiring(true);
      await driverService.deleteDriver(driver.driver_id);
      setIsFireModalOpen(false);
      navigate('/drivers');
    } catch (err) {
      console.error('Failed to fire driver:', err);
      alert(err.message || 'Failed to remove driver from fleet.');
    } finally {
      setFiring(false);
    }
  };

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

          {/* Right Side: Assigned Commercial Vehicle Box & Profile / Fire Driver Actions */}
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

            <div className="flex sm:flex-col gap-2">
              <button
                onClick={() => setIsModalOpen(true)}
                className="flex-1 inline-flex items-center justify-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-semibold text-blue-700 bg-blue-50 hover:bg-blue-100 border border-blue-200 transition-colors shrink-0"
              >
                <UserCheck className="w-4 h-4 text-blue-600" />
                <span>{hasProfileInfo ? 'Edit Profile' : 'Complete Profile'}</span>
              </button>

              <button
                onClick={() => setIsFireModalOpen(true)}
                className="flex-1 inline-flex items-center justify-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-semibold text-rose-700 bg-rose-50 hover:bg-rose-100 border border-rose-200 transition-colors shrink-0"
              >
                <UserX className="w-4 h-4 text-rose-600" />
                <span>Fire Driver</span>
              </button>
            </div>
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

      {/* Fire Driver Confirmation Modal */}
      {isFireModalOpen && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-xs z-50 flex items-center justify-center p-4">
          <div className="bg-white border border-slate-200 rounded-2xl p-6 sm:p-7 max-w-lg w-full shadow-2xl animate-in zoom-in-95">
            <div className="w-12 h-12 rounded-2xl bg-rose-50 text-rose-600 border border-rose-200 flex items-center justify-center mx-auto mb-4">
              <AlertTriangle className="w-6 h-6" />
            </div>

            <h3 className="text-xl font-bold text-slate-900 text-center mb-2">Fire Driver?</h3>
            <p className="text-xs sm:text-sm text-slate-600 text-center leading-relaxed mb-6">
              This will permanently remove this driver&apos;s fleet record, assigned vehicle relationship, trips, monitoring sessions, incidents, alerts, evidence references, analytics records, and authentication/biometric registration.
            </p>

            <div className="flex gap-3 justify-end">
              <button
                disabled={firing}
                onClick={() => setIsFireModalOpen(false)}
                className="px-4 py-2 text-xs font-semibold text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-lg transition"
              >
                Cancel
              </button>
              <button
                disabled={firing}
                onClick={handleConfirmFire}
                className="px-4 py-2 text-xs font-semibold text-white bg-rose-600 hover:bg-rose-700 rounded-lg transition flex items-center gap-1.5"
              >
                {firing ? 'Removing Driver...' : 'Yes, Fire Driver'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

