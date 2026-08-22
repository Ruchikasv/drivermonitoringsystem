import React, { useState, useEffect, useMemo } from 'react';
import AlertFilterBar from '../components/alerts/AlertFilterBar';
import AlertListTable from '../components/alerts/AlertListTable';
import StatCard from '../components/common/StatCard';
import LoadingState from '../components/common/LoadingState';
import ErrorState from '../components/common/ErrorState';
import { alertService } from '../services/alertService';
import { driverService } from '../services/driverService';
import { AlertTriangle, AlertOctagon, Info, ShieldAlert } from 'lucide-react';

export default function AlertsPage() {
  const [alerts, setAlerts] = useState([]);
  const [drivers, setDrivers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [search, setSearch] = useState('');
  const [level, setLevel] = useState('ALL');
  const [driverId, setDriverId] = useState('ALL');

  const loadData = async () => {
    try {
      setLoading(true);
      setError(null);
      const [a, d] = await Promise.all([
        alertService.getAlerts(),
        driverService.getDrivers(),
      ]);
      setAlerts(a);
      setDrivers(d);
    } catch (err) {
      setError(err.message || 'Failed to retrieve safety alerts.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const filteredAlerts = useMemo(() => {
    return alerts.filter((a) => {
      const matchesLevel = level === 'ALL' || a.level === Number(level);
      const matchesDriver = driverId === 'ALL' || a.driver_id === Number(driverId);
      const query = search.toLowerCase().trim();
      const matchesSearch =
        !query ||
        a.alert_id.toLowerCase().includes(query) ||
        a.driver_name.toLowerCase().includes(query) ||
        a.event_type.toLowerCase().includes(query) ||
        a.location.toLowerCase().includes(query) ||
        a.vehicle_plate.toLowerCase().includes(query);

      return matchesLevel && matchesDriver && matchesSearch;
    });
  }, [alerts, search, level, driverId]);

  const levelCounts = useMemo(() => {
    return {
      level1: alerts.filter((a) => a.level === 1).length,
      level2: alerts.filter((a) => a.level === 2).length,
      level3: alerts.filter((a) => a.level === 3).length,
    };
  }, [alerts]);

  if (loading) return <LoadingState message="Loading fleet safety alerts…" />;
  if (error) return <ErrorState message={error} onRetry={loadData} />;

  return (
    <div className="space-y-6">
      {/* Notice Banner */}
      <div className="p-3.5 rounded-xl bg-slate-100 border border-slate-200 text-xs text-slate-700 flex items-start gap-2.5">
        <ShieldAlert className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
        <div>
          <span className="font-bold text-slate-900 block text-xs">
            Safety Alert Console (Demo Incidents Simulation)
          </span>
          <p className="mt-0.5 text-slate-600">
            Alert entries below demonstrate Level 1, 2, and 3 incident handling and dispatch logs. Real-time infraction triggers will connect to the Phase 2 CV and MQ-3 hardware bus.
          </p>
        </div>
      </div>

      {/* 3 Tier Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard
          title="Level 1: Minor Warnings"
          value={levelCounts.level1}
          subtitle="Distraction & early yawn prompts"
          icon={Info}
          iconColor="text-amber-700 bg-amber-50"
        />
        <StatCard
          title="Level 2: Moderate Alerts"
          value={levelCounts.level2}
          subtitle="Prolonged eye closures & audio chimes"
          icon={AlertTriangle}
          iconColor="text-orange-700 bg-orange-50"
        />
        <StatCard
          title="Level 3: Critical Hazards"
          value={levelCounts.level3}
          subtitle="Microsleep & immediate safety holds"
          icon={AlertOctagon}
          iconColor="text-red-700 bg-red-50"
        />
      </div>

      {/* Filter and Query Controls */}
      <AlertFilterBar
        search={search}
        onSearchChange={setSearch}
        level={level}
        onLevelChange={setLevel}
        driverId={driverId}
        onDriverChange={setDriverId}
        drivers={drivers}
      />

      {/* Table of Incidents */}
      <AlertListTable alerts={filteredAlerts} />
    </div>
  );
}
