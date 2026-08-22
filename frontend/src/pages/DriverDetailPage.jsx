import React, { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import DriverProfileHeader from '../components/drivers/DriverProfileHeader';
import StatCard from '../components/common/StatCard';
import Card from '../components/common/Card';
import SafetyScore from '../components/common/SafetyScore';
import AlertLevelBadge from '../components/common/AlertLevelBadge';
import EmptyState from '../components/common/EmptyState';
import LoadingState from '../components/common/LoadingState';
import ErrorState from '../components/common/ErrorState';
import { driverService } from '../services/driverService';
import { tripService } from '../services/tripService';
import { alertService } from '../services/alertService';
import { formatDateTime, formatDuration } from '../utils/formatters';
import {
  ArrowLeft,
  Route,
  Clock,
  AlertTriangle,
  Wine,
  ShieldCheck,
  CheckCircle2,
  MapPin,
} from 'lucide-react';

export default function DriverDetailPage() {
  const { id } = useParams();
  const [driver, setDriver] = useState(null);
  const [trips, setTrips] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const loadDriverDetails = async () => {
    try {
      setLoading(true);
      setError(null);
      const [d, t, a] = await Promise.all([
        driverService.getDriverById(id),
        tripService.getTrips({ driver_id: id }),
        alertService.getAlerts({ driver_id: id }),
      ]);
      if (!d) {
        throw new Error(`Driver with ID #${id} was not found in the fleet registry.`);
      }
      setDriver(d);

      // Only display trips/alerts belonging to this driver ID
      const driverTrips = t.filter((item) => item.driver_id === Number(id));
      const driverAlerts = a.filter((item) => item.driver_id === Number(id));

      setTrips(driverTrips);
      setAlerts(driverAlerts);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDriverDetails();
  }, [id]);

  const handleProfileUpdated = async (updatedFields) => {
    const updated = await driverService.updateDriverProfile(id, updatedFields);
    if (updated) {
      setDriver(updated);
    }
  };

  if (loading) return <LoadingState message="Loading driver dossier…" />;
  if (error) return <ErrorState message={error} onRetry={loadDriverDetails} />;

  return (
    <div className="space-y-6">
      {/* Back Navigation Bar */}
      <div>
        <Link
          to="/drivers"
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-600 hover:text-slate-900 bg-white border border-slate-200 px-3 py-1.5 rounded-lg shadow-2xs transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          Back to Drivers List
        </Link>
      </div>

      {/* Driver Identity Card */}
      <DriverProfileHeader driver={driver} onProfileUpdated={handleProfileUpdated} />

      {/* 5 Key Metric Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
        <StatCard
          title="Safety Score"
          value={<SafetyScore score={driver.safety_score} size="sm" />}
          subtitle="Fleet compliance rating"
          icon={ShieldCheck}
          iconColor="text-emerald-600 bg-emerald-50"
        />
        <StatCard
          title="Total Trips"
          value={driver.total_trips !== null && driver.total_trips !== undefined ? driver.total_trips : '—'}
          subtitle={driver.total_trips !== null ? 'Commercial assignments' : 'No real trip records'}
          icon={Route}
          iconColor="text-blue-600 bg-blue-50"
        />
        <StatCard
          title="Driving Hours"
          value={driver.driving_hours !== null && driver.driving_hours !== undefined ? `${driver.driving_hours}h` : '—'}
          subtitle={driver.driving_hours !== null ? 'Cumulative road time' : 'No real driving-session data'}
          icon={Clock}
          iconColor="text-slate-700 bg-slate-100"
        />
        <StatCard
          title="Drowsiness Events"
          value={driver.drowsiness_events !== null && driver.drowsiness_events !== undefined ? driver.drowsiness_events : '—'}
          subtitle={driver.drowsiness_events !== null ? 'EAR/PERCLOS triggers' : 'Awaiting Phase 2 monitoring'}
          icon={AlertTriangle}
          iconColor="text-amber-600 bg-amber-50"
        />
        <StatCard
          title="Alcohol Events"
          value={driver.alcohol_events !== null && driver.alcohol_events !== undefined ? driver.alcohol_events : '—'}
          subtitle={driver.alcohol_events !== null ? 'MQ-3 sensor alerts' : 'Awaiting Phase 2 sensor'}
          icon={Wine}
          iconColor="text-red-600 bg-red-50"
        />
      </div>

      {/* 2 Column Details: Trips and Alerts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent Trips */}
        <Card
          title="Assigned Commercial Trips"
          subtitle={`History of transport dispatches for ${driver.name}`}
        >
          {trips.length === 0 ? (
            <EmptyState
              title="No real trip records available yet"
              description={
                driver.isRegisteredBackend
                  ? 'This driver is registered in SQLite drivers.db, but commercial route dispatches have not been logged yet.'
                  : 'This driver has no logged trips yet.'
              }
            />
          ) : (
            <div className="divide-y divide-slate-100">
              {trips.map((trip) => (
                <div key={trip.trip_id} className="py-3 flex items-start justify-between gap-3">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="font-mono font-bold text-slate-900 text-xs">{trip.trip_id}</span>
                      <span className="text-slate-400">•</span>
                      <span className="text-xs font-semibold text-slate-700">
                        {trip.origin} ➔ {trip.destination}
                      </span>
                    </div>
                    <div className="flex items-center gap-3 text-[11px] text-slate-500">
                      <span>{formatDateTime(trip.start_time)}</span>
                      <span>({formatDuration(trip.duration_minutes)})</span>
                    </div>
                  </div>
                  <div className="text-right">
                    <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-slate-100 text-slate-700">
                      {trip.status}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* Driver Alerts */}
        <Card
          title="Safety & Infraction History"
          subtitle={`Audited incidents and sensor triggers for ${driver.name}`}
        >
          {alerts.length === 0 ? (
            <EmptyState
              title="No real safety incidents recorded yet"
              description={
                driver.isRegisteredBackend
                  ? 'Real-time eye/head tracking and MQ-3 alcohol telemetry will log infraction incidents during Phase 2.'
                  : 'This driver has maintained a clean incident record.'
              }
              icon={CheckCircle2}
            />
          ) : (
            <div className="divide-y divide-slate-100">
              {alerts.map((alert) => (
                <div key={alert.alert_id} className="py-3 space-y-1.5">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <AlertLevelBadge level={alert.level} />
                      <span className="font-mono text-slate-400 text-xs">{alert.alert_id}</span>
                    </div>
                    <span className="text-xs text-slate-500">{formatDateTime(alert.timestamp)}</span>
                  </div>
                  <div className="text-xs font-semibold text-slate-800">{alert.event_type}</div>
                  <div className="flex items-center justify-between text-[11px] text-slate-500">
                    <span className="flex items-center gap-1">
                      <MapPin className="w-3 h-3 text-slate-400" />
                      {alert.location}
                    </span>
                    <span className="italic text-slate-400">{alert.notes}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
