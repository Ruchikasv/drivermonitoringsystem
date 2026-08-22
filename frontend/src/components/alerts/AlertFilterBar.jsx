import React from 'react';
import { Search, Filter } from 'lucide-react';

export default function AlertFilterBar({
  search = '',
  onSearchChange,
  level = 'ALL',
  onLevelChange,
  driverId = 'ALL',
  onDriverChange,
  drivers = [],
}) {
  return (
    <div className="flex flex-col md:flex-row items-center justify-between gap-3 bg-white p-4 rounded-xl border border-slate-200 shadow-subtle">
      {/* Search Input */}
      <div className="relative w-full md:w-80">
        <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
        <input
          type="text"
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="Search alert event, driver or location…"
          className="w-full pl-9 pr-4 py-2 text-xs rounded-lg border border-slate-200 bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-colors"
        />
      </div>

      {/* Filter Selectors */}
      <div className="flex items-center gap-2.5 w-full md:w-auto flex-wrap">
        <div className="flex items-center gap-1.5">
          <Filter className="w-3.5 h-3.5 text-slate-400" />
          <select
            value={level}
            onChange={(e) => onLevelChange(e.target.value)}
            className="text-xs py-2 px-3 rounded-lg border border-slate-200 bg-slate-50 text-slate-700 font-medium focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-colors"
          >
            <option value="ALL">All Alert Levels</option>
            <option value="1">Level 1 — Low Warning</option>
            <option value="2">Level 2 — Moderate Alert</option>
            <option value="3">Level 3 — Critical Hazard</option>
          </select>
        </div>

        <select
          value={driverId}
          onChange={(e) => onDriverChange(e.target.value)}
          className="text-xs py-2 px-3 rounded-lg border border-slate-200 bg-slate-50 text-slate-700 font-medium focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-colors"
        >
          <option value="ALL">All Drivers</option>
          {drivers.map((d) => (
            <option key={d.driver_id} value={d.driver_id}>
              {d.name} (#{d.driver_id})
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}
