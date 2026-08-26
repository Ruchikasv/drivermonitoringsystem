import React, { useState, useEffect } from 'react';
import StatCard from '../components/common/StatCard';
import Card from '../components/common/Card';
import LoadingState from '../components/common/LoadingState';
import ErrorState from '../components/common/ErrorState';
import ActiveDriverTable from '../components/dashboard/ActiveDriverTable';
import RecentAlertsSection from '../components/dashboard/RecentAlertsSection';
import DrowsinessTrendChart from '../components/dashboard/DrowsinessTrendChart';
import { driverService } from '../services/driverService';
import { alertService } from '../services/alertService';
import { analyticsService } from '../services/analyticsService';
import { Users, Truck, AlertTriangle, ShieldCheck, Route, Clock } from 'lucide-react';

export default function DashboardPage() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [activeDrivers, setActiveDrivers] = useState([]);
  const [recentAlerts, setRecentAlerts] = useState([]);
  const [drowsinessTrend, setDrowsinessTrend] = useState([]);

  const loadData = async () => {
    try {
      setLoading(true);
      setError(null);
      const [m, drivers, alerts, trend] = await Promise.all([
        analyticsService.getFleetMetrics(),
        driverService.getActiveDrivers(),
        alertService.getRecentAlerts(4),
        analyticsService.getDrowsinessTrend(),
      ]);
      setMetrics(m);
      setActiveDrivers(drivers);
      setRecentAlerts(alerts);
      setDrowsinessTrend(trend);
    } catch (err) {
      setError(err.message || 'Failed to retrieve dashboard telemetry.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  if (loading) return <LoadingState message="Loading fleet overview telemetry…" />;
  if (error) return <ErrorState message={error} onRetry={loadData} />;

  return (
    <div className="space-y-6">
      {/* 4 Stat Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Total Registered Drivers"
          value={metrics.totalDrivers}
          subtitle="Enrolled in SQLite database"
          icon={Users}
          iconColor="text-slate-700 bg-slate-100"
        />
        <StatCard
          title="Active on Route"
          value={activeDrivers.length}
          subtitle="Currently monitored sessions"
          icon={Truck}
          iconColor="text-blue-600 bg-blue-50"
        />
        <StatCard
          title="Total Safety Infractions"
          value={metrics.todayAlerts}
          subtitle={`${metrics.critical_incidents || 0} Critical • ${metrics.warning_incidents || 0} Warning`}
          icon={AlertTriangle}
          iconColor="text-amber-600 bg-amber-50"
        />
        <StatCard
          title="Fleet Safety Index"
          value={`${metrics.fleetSafetyScore}%`}
          subtitle="Fleet average benchmark"
          icon={ShieldCheck}
          iconColor="text-emerald-600 bg-emerald-50"
        />
      </div>

      {/* Row 2: Drowsiness Trend Chart + Recent Alerts */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Drowsiness Trend (2 columns) */}
        <div className="lg:col-span-2">
          <Card
            title="7-Day Safety Incident History"
            subtitle="Daily breakdown of Level 1-3 fatigue alerts recorded across all fleet trips"
          >
            <DrowsinessTrendChart data={drowsinessTrend} />
            <div className="mt-3 pt-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
              <span className="flex items-center gap-1.5 font-medium text-emerald-800 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200 text-[11px]">
                <span className="w-2 h-2 rounded-full bg-emerald-500" />
                Live Monitoring Pipeline Active
              </span>
              <span className="text-[11px] text-slate-400">Multi-Modal CV Fusion Telemetry</span>
            </div>
          </Card>
        </div>

        {/* Recent Alerts (1 column) */}
        <div>
          <Card
            title="Live Alert Feed"
            subtitle="Recent multi-level safety incidents"
          >
            <RecentAlertsSection alerts={recentAlerts} />
          </Card>
        </div>
      </div>

      {/* Row 3: Active Commercial Drivers */}
      <div>
        <Card
          title="Active Route Drivers"
          subtitle="Real-time status of commercial vehicles currently in transit"
        >
          <ActiveDriverTable drivers={activeDrivers} />
        </Card>
      </div>
    </div>
  );
}
