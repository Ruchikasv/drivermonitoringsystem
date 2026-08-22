import React from 'react';
import { Wine, AlertCircle, Clock, BellRing, Radio } from 'lucide-react';

export default function SensorStatusPanel() {
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-subtle space-y-4">
      <div className="flex items-center justify-between border-b border-slate-100 pb-3">
        <div>
          <h3 className="font-bold text-slate-900 text-sm">Sensory & Hardware Bus</h3>
          <p className="text-xs text-slate-500">In-cabin alcohol sensing & tiered alert matrix</p>
        </div>
        <div className="flex items-center gap-1.5 text-[11px] font-semibold text-slate-600 bg-slate-100 px-2.5 py-1 rounded-md border border-slate-200">
          <Clock className="w-3.5 h-3.5 text-slate-500" />
          <span>Hardware Standby (Phase 2)</span>
        </div>
      </div>

      <div className="space-y-3">
        {/* Alcohol Sensor (MQ3) */}
        <div className="p-3.5 rounded-lg border border-slate-200 bg-slate-50/50 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-slate-200 text-slate-600">
              <Wine className="w-4 h-4" />
            </div>
            <div>
              <h4 className="text-xs font-bold text-slate-900">MQ-3 Alcohol Sensor</h4>
              <p className="text-[11px] text-slate-500">ADC Serial Interface Bus • BAC Telemetry</p>
            </div>
          </div>
          <div className="text-left sm:text-right">
            <span className="inline-flex items-center gap-1 text-xs font-semibold text-amber-800 bg-amber-50 border border-amber-200 px-2.5 py-1 rounded-md">
              <AlertCircle className="w-3.5 h-3.5 text-amber-600" />
              Sensor Not Connected (Awaiting Phase 2)
            </span>
          </div>
        </div>

        {/* 3-Tier Alert Protocol Status */}
        <div className="p-3.5 rounded-lg border border-slate-200 bg-slate-50/50 space-y-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-blue-100/70 text-blue-700">
                <BellRing className="w-4 h-4" />
              </div>
              <div>
                <h4 className="text-xs font-bold text-slate-900">Active Alert Protocol</h4>
                <p className="text-[11px] text-slate-500">3-Tier Progressive Alert Matrix</p>
              </div>
            </div>
            <span className="text-xs font-bold text-slate-700 bg-white border border-slate-200 px-2 py-0.5 rounded shadow-2xs">
              STANDBY (Awaiting Phase 2)
            </span>
          </div>

          <div className="grid grid-cols-3 gap-2 pt-1">
            <div className="p-2 rounded border border-amber-200/60 bg-amber-50/40 text-center">
              <span className="text-[10px] font-bold text-amber-800 block">Level 1 (Soft)</span>
              <span className="text-[9px] text-amber-600">Visual Indicator</span>
            </div>
            <div className="p-2 rounded border border-orange-200/60 bg-orange-50/40 text-center">
              <span className="text-[10px] font-bold text-orange-800 block">Level 2 (Moderate)</span>
              <span className="text-[9px] text-orange-600">Audio Chime + Log</span>
            </div>
            <div className="p-2 rounded border border-red-200/60 bg-red-50/40 text-center">
              <span className="text-[10px] font-bold text-red-800 block">Level 3 (Critical)</span>
              <span className="text-[9px] text-red-600">Siren + Fleet Hold</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
