import React, { useState, useEffect, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import DriverFilterBar from '../components/drivers/DriverFilterBar';
import DriverListTable from '../components/drivers/DriverListTable';
import LoadingState from '../components/common/LoadingState';
import ErrorState from '../components/common/ErrorState';
import { driverService } from '../services/driverService';
import { ShieldCheck } from 'lucide-react';

export default function DriversPage() {
  const [searchParams] = useSearchParams();
  const [drivers, setDrivers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState(searchParams.get('search') || '');
  const [status, setStatus] = useState('ALL');

  useEffect(() => {
    const q = searchParams.get('search');
    if (q !== null) {
      setSearch(q);
    }
  }, [searchParams]);

  const loadDrivers = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await driverService.getDrivers();
      setDrivers(data);
    } catch (err) {
      setError(err.message || 'Failed to load driver roster.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDrivers();
  }, []);

  const filteredDrivers = useMemo(() => {
    return drivers.filter((d) => {
      const matchesStatus =
        status === 'ALL' ||
        d.status === status ||
        (status === 'ACTIVE' && d.status === 'ON_ROUTE') ||
        (status === 'ON_ROUTE' && d.status === 'ACTIVE') ||
        !d.status;
      const query = search.toLowerCase().trim();

      const regNumber = d.vehicle ? d.vehicle.registration_number : (d.vehicle_plate || '');
      const vehicleModel = d.vehicle ? d.vehicle.model : (d.assigned_vehicle || '');

      const matchesSearch =
        !query ||
        d.name.toLowerCase().includes(query) ||
        String(d.driver_id).includes(query) ||
        regNumber.toLowerCase().includes(query) ||
        vehicleModel.toLowerCase().includes(query) ||
        (d.phone && d.phone.toLowerCase().includes(query));

      return matchesStatus && matchesSearch;
    });
  }, [drivers, search, status]);

  if (loading) return <LoadingState message="Loading driver profiles…" />;
  if (error) return <ErrorState message={error} onRetry={loadDrivers} />;

  return (
    <div className="space-y-6">
      {/* Notice Banner explaining Phase 1 Backend Connection */}
      <div className="p-4 rounded-xl bg-blue-50 border border-blue-100 flex items-start gap-3 text-xs text-blue-900">
        <ShieldCheck className="w-5 h-5 text-blue-600 shrink-0 mt-0.5" />
        <div>
          <span className="font-bold text-sm block text-blue-950">
            Phase 1 Facial Authentication Verified Driver: Ruchika (ID #1)
          </span>
          <p className="mt-0.5 text-blue-800">
            Driver ID #1 (Ruchika) is registered in the SQLite biometric database. The UI is connected to query and display registered fleet records alongside commercial tracking data.
          </p>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <DriverFilterBar
        search={search}
        onSearchChange={setSearch}
        status={status}
        onStatusChange={setStatus}
      />

      {/* Drivers Roster Table */}
      <DriverListTable drivers={filteredDrivers} />
    </div>
  );
}
