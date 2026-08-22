import React, { useState } from 'react';
import CameraFeedPlaceholder from '../components/monitoring/CameraFeedPlaceholder';
import TelemetryCard from '../components/monitoring/TelemetryCard';
import SensorStatusPanel from '../components/monitoring/SensorStatusPanel';
import Card from '../components/common/Card';
import { ShieldCheck, AlertCircle, Eye, RefreshCw, Radio, UserCheck } from 'lucide-react';

export default function LiveMonitoringPage() {
  const [selectedDriver, setSelectedDriver] = useState({
    name: 'Ruchika',
    driver_id: 1,
    vehicle_plate: 'KA-01-MJ-8821',
  });

  return (
    <div className="space-y-6">
      {/* Explicit Phase 2 Status Notice */}
      <div className="p-4 rounded-xl bg-amber-50 border border-amber-200 text-xs text-amber-950 flex items-start gap-3">
        <AlertCircle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
        <div>
          <h4 className="font-bold text-sm text-amber-900">
            Phase 1 Integration Status: Facial Authentication Enabled • AI/Sensors in Standby
          </h4>
          <p className="mt-1 text-amber-800 leading-relaxed">
            The laptop webcam facial authentication module (Phase 1) is registered and ready.
            Computer vision telemetry (EAR, MAR, PERCLOS, Head Pose) and hardware sensor telemetry (MQ-3 alcohol detection) are <strong>awaiting the Phase 2 monitoring pipeline</strong>. The layout below serves as the real-time operational interface.
          </p>
        </div>
      </div>

      {/* Driver & Stream Selector Bar */}
      <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-subtle flex flex-col sm:flex-row items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-lg bg-blue-50 text-blue-600">
            <Radio className="w-5 h-5 animate-pulse" />
          </div>
          <div>
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider block">
              Active Monitoring Target
            </span>
            <div className="flex items-center gap-2">
              <span className="text-base font-bold text-slate-900">{selectedDriver.name}</span>
              <span className="font-mono text-xs font-semibold px-2 py-0.5 rounded bg-slate-100 text-slate-700">
                Driver ID #{selectedDriver.driver_id}
              </span>
              <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                <ShieldCheck className="w-3 h-3" />
                Auth Verified
              </span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 text-xs text-slate-600">
          <span className="font-medium">Assigned Commercial Unit:</span>
          <span className="font-mono font-bold text-slate-900 bg-slate-100 px-2 py-1 rounded">
            {selectedDriver.vehicle_plate}
          </span>
        </div>
      </div>

      {/* Main Monitoring Grid: Video Feed + Telemetry Cards */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Camera Feed Stream (7 Columns) */}
        <div className="lg:col-span-7">
          <CameraFeedPlaceholder
            driverName={selectedDriver.name}
            driverId={selectedDriver.driver_id}
            vehiclePlate={selectedDriver.vehicle_plate}
            cameraIndex={0}
          />
        </div>

        {/* Real-Time Telemetry & Sensory Gauges (5 Columns) */}
        <div className="lg:col-span-5 space-y-6">
          <TelemetryCard />
          <SensorStatusPanel />
        </div>
      </div>
    </div>
  );
}
