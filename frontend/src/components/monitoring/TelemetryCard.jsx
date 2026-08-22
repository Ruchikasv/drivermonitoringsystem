import React from 'react';
import { Eye, Smile, Percent, Compass, Info, Clock } from 'lucide-react';

const METRICS = [
  {
    key: 'ear',
    name: 'EAR',
    fullName: 'Eye Aspect Ratio',
    value: 'N/A',
    subValue: 'Awaiting Phase 2',
    threshold: 'Target Threshold: <0.20',
    status: 'Standby',
    statusColor: 'text-slate-600 bg-slate-100 border-slate-200',
    icon: Eye,
  },
  {
    key: 'mar',
    name: 'MAR',
    fullName: 'Mouth Aspect Ratio',
    value: 'N/A',
    subValue: 'Awaiting Phase 2',
    threshold: 'Target Threshold: >0.65 (Yawn)',
    status: 'Standby',
    statusColor: 'text-slate-600 bg-slate-100 border-slate-200',
    icon: Smile,
  },
  {
    key: 'perclos',
    name: 'PERCLOS',
    fullName: 'Eye Closure % (60s)',
    value: 'N/A',
    subValue: 'Awaiting Phase 2',
    threshold: 'Target Threshold: >15.0%',
    status: 'Standby',
    statusColor: 'text-slate-600 bg-slate-100 border-slate-200',
    icon: Percent,
  },
  {
    key: 'pose',
    name: 'Head Pose',
    fullName: 'Pitch / Yaw / Roll',
    value: 'N/A',
    subValue: 'Awaiting Phase 2',
    threshold: 'Forward Facing Deviation',
    status: 'Standby',
    statusColor: 'text-slate-600 bg-slate-100 border-slate-200',
    icon: Compass,
  },
];

export default function TelemetryCard() {
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-subtle space-y-4">
      <div className="flex items-center justify-between border-b border-slate-100 pb-3">
        <div>
          <h3 className="font-bold text-slate-900 text-sm">Computer Vision Telemetry</h3>
          <p className="text-xs text-slate-500">Real-time facial geometry & landmark tracking</p>
        </div>
        <div className="flex items-center gap-1.5 text-[11px] font-semibold text-amber-800 bg-amber-50 px-2.5 py-1 rounded-md border border-amber-200">
          <Clock className="w-3.5 h-3.5 text-amber-600" />
          <span>Awaiting Phase 2 CV Pipeline</span>
        </div>
      </div>

      {/* 4 Metric Cards Grid */}
      <div className="grid grid-cols-2 gap-3">
        {METRICS.map((metric) => {
          const Icon = metric.icon;
          return (
            <div
              key={metric.key}
              className="p-3.5 rounded-lg border border-slate-200 bg-slate-50/70 space-y-2"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <Icon className="w-4 h-4 text-slate-500" />
                  <span className="text-xs font-bold text-slate-800">{metric.name}</span>
                </div>
                <span
                  className={`text-[10px] font-semibold px-2 py-0.5 rounded border ${metric.statusColor}`}
                >
                  {metric.status}
                </span>
              </div>

              <div>
                <div className="text-xl font-extrabold text-slate-400 font-mono">
                  {metric.value}
                </div>
                <p className="text-[11px] text-amber-700 font-medium">{metric.subValue}</p>
                <p className="text-[10px] text-slate-500 font-medium">{metric.fullName}</p>
              </div>

              <div className="text-[10px] text-slate-400 border-t border-slate-200/60 pt-1 font-mono">
                {metric.threshold}
              </div>
            </div>
          );
        })}
      </div>

      <div className="p-3 rounded-lg bg-slate-50 border border-slate-200 text-[11px] text-slate-700 flex items-start gap-2">
        <Info className="w-4 h-4 text-blue-600 shrink-0 mt-0.5" />
        <div>
          <span className="font-semibold block text-slate-900">Computer Vision Telemetry Status</span>
          <span>
            EAR, MAR, PERCLOS, and Head Pose calculations will stream live from the MediaPipe/OpenCV facial mesh pipeline in Phase 2. No synthetic values are presented as real sensor measurements.
          </span>
        </div>
      </div>
    </div>
  );
}
