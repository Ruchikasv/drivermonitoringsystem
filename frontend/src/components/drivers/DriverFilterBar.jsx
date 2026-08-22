import React from 'react';
import { Search, Filter } from 'lucide-react';

export default function DriverFilterBar({
  search = '',
  onSearchChange,
  status = 'ALL',
  onStatusChange,
}) {
  return (
    <div className="flex flex-col sm:flex-row items-center justify-between gap-3 bg-white p-4 rounded-xl border border-slate-200 shadow-subtle">
      {/* Search Input */}
      <div className="relative w-full sm:w-80">
        <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
        <input
          type="text"
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="Filter by driver name, ID, or vehicle…"
          className="w-full pl-9 pr-4 py-2 text-xs rounded-lg border border-slate-200 bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-colors"
        />
      </div>

      {/* Filter Options */}
      <div className="flex items-center gap-2 w-full sm:w-auto">
        <Filter className="w-3.5 h-3.5 text-slate-400" />
        <select
          value={status}
          onChange={(e) => onStatusChange(e.target.value)}
          className="text-xs py-2 px-3 rounded-lg border border-slate-200 bg-slate-50 text-slate-700 font-medium focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-colors"
        >
          <option value="ALL">All Statuses</option>
          <option value="ACTIVE">Active on Route</option>
          <option value="RESTING">On Break</option>
          <option value="OFF_DUTY">Off Duty</option>
          <option value="SUSPENDED">Safety Hold</option>
        </select>
      </div>
    </div>
  );
}
