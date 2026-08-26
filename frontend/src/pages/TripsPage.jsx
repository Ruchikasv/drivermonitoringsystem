import React, { useState, useEffect, useMemo } from 'react';
import TripHistoryTable from '../components/trips/TripHistoryTable';
import LoadingState from '../components/common/LoadingState';
import ErrorState from '../components/common/ErrorState';
import { tripService } from '../services/tripService';
import { Search, Filter, Route, Clock, CheckCircle2 } from 'lucide-react';

export default function TripsPage() {
  const [trips, setTrips] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('ALL');

  const loadTrips = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await tripService.getTrips();
      setTrips(data);
    } catch (err) {
      setError(err.message || 'Failed to fetch trip records.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadTrips();
  }, []);

  const filteredTrips = useMemo(() => {
    return trips.filter((t) => {
      const matchesStatus = status === 'ALL' || t.status === status;
      const query = search.toLowerCase().trim();
      const matchesSearch =
        !query ||
        t.trip_id.toLowerCase().includes(query) ||
        t.driver_name.toLowerCase().includes(query) ||
        t.origin.toLowerCase().includes(query) ||
        t.destination.toLowerCase().includes(query) ||
        t.vehicle_plate.toLowerCase().includes(query);

      return matchesStatus && matchesSearch;
    });
  }, [trips, search, status]);

  if (loading) return <LoadingState message="Loading commercial trip dispatches…" />;
  if (error) return <ErrorState message={error} onRetry={loadTrips} />;

  return (
    <div className="space-y-6">
      {/* Notice Banner */}
      <div className="p-3.5 rounded-xl bg-blue-50 border border-blue-100 text-xs text-blue-900 flex items-start gap-2.5">
        <Route className="w-4 h-4 text-blue-600 shrink-0 mt-0.5" />
        <div>
          <span className="font-bold text-blue-950 block text-xs">
            Commercial Fleet Monitoring & Trip Dispatches
          </span>
          <p className="mt-0.5 text-blue-800">
            Trip logs reflect active and completed monitoring sessions from the database. Duration, driver safety scores, and vehicle telemetry are synchronized in real time.
          </p>
        </div>
      </div>

      {/* Top Filter Bar */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-3 bg-white p-4 rounded-xl border border-slate-200 shadow-subtle">
        <div className="relative w-full sm:w-80">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search trip ID, driver, origin, destination…"
            className="w-full pl-9 pr-4 py-2 text-xs rounded-lg border border-slate-200 bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-colors"
          />
        </div>

        <div className="flex items-center gap-2 w-full sm:w-auto">
          <Filter className="w-3.5 h-3.5 text-slate-400" />
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="text-xs py-2 px-3 rounded-lg border border-slate-200 bg-slate-50 text-slate-700 font-medium focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 transition-colors"
          >
            <option value="ALL">All Trip Statuses</option>
            <option value="RUNNING">In Progress (Active)</option>
            <option value="PAUSED">Paused (Standby)</option>
            <option value="COMPLETED">Completed</option>
          </select>
        </div>
      </div>

      {/* Trips Table */}
      <TripHistoryTable trips={filteredTrips} />
    </div>
  );
}
