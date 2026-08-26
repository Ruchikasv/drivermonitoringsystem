import React, { useState, useEffect } from 'react';
import Card from '../components/common/Card';
import LoadingState from '../components/common/LoadingState';
import ErrorState from '../components/common/ErrorState';
import EmptyState from '../components/common/EmptyState';
import { analyticsService } from '../services/analyticsService';
import { driverService } from '../services/driverService';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
} from 'recharts';
import { BarChart3, TrendingUp, ShieldAlert, Award, Clock, ShieldCheck, Users } from 'lucide-react';

export default function AnalyticsPage() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [alertsByDriver, setAlertsByDriver] = useState([]);
  const [scoreDistribution, setScoreDistribution] = useState([]);
  const [drivers, setDrivers] = useState([]);

  const loadAnalytics = async () => {
    try {
      setLoading(true);
      setError(null);
      const [m, alerts, scores, drvs] = await Promise.all([
        analyticsService.getFleetMetrics(),
        analyticsService.getAlertsByDriver(),
        analyticsService.getScoreDistribution(),
        driverService.getDrivers(),
      ]);
      setMetrics(m);
      setAlertsByDriver(alerts || []);
      setScoreDistribution(scores || []);
      setDrivers(drvs || []);
    } catch (err) {
      setError(err.message || 'Failed to retrieve fleet analytics.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAnalytics();
  }, []);

  if (loading) return <LoadingState message="Aggregating fleet safety analytics…" />;
  if (error) return <ErrorState message={error} onRetry={loadAnalytics} />;

  const totalScoreCount = scoreDistribution.reduce((acc, curr) => acc + (curr.count || 0), 0);
  const topDrivers = [...drivers].sort((a, b) => (b.safety_score || 0) - (a.safety_score || 0)).slice(0, 3);

  return (
    <div className="space-y-6">
      {/* 2 Column Charts: Alerts by Driver & Safety Score Distribution */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Alerts by Driver Bar Chart */}
        <Card
          title="Safety Infractions by Driver"
          subtitle="Total recorded Level 1-3 fatigue & distraction incidents from database"
        >
          {alertsByDriver.length === 0 ? (
            <div className="h-64 flex items-center justify-center">
              <EmptyState title="No infraction data recorded" description="No safety infractions logged in database yet." />
            </div>
          ) : (
            <div className="h-64 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={alertsByDriver} margin={{ top: 10, right: 10, left: -20, bottom: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
                  <XAxis
                    dataKey="name"
                    tick={{ fontSize: 11, fill: '#64748b' }}
                    axisLine={{ stroke: '#e2e8f0' }}
                    tickLine={false}
                    interval={0}
                    angle={-15}
                    textAnchor="end"
                  />
                  <YAxis
                    tick={{ fontSize: 11, fill: '#64748b' }}
                    axisLine={false}
                    tickLine={false}
                    allowDecimals={false}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#ffffff',
                      borderColor: '#e2e8f0',
                      borderRadius: '0.5rem',
                      boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)',
                      fontSize: '12px',
                    }}
                    formatter={(value) => [`${value} Events`, 'Infractions']}
                  />
                  <Bar dataKey="count" fill="#2563eb" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>

        {/* Safety Score Distribution Donut */}
        <Card
          title="Fleet Safety Rating Distribution"
          subtitle="Commercial driver score breakdown across benchmark tiers"
        >
          {totalScoreCount === 0 ? (
            <div className="h-64 flex items-center justify-center">
              <EmptyState title="No safety score data" description="Complete monitoring sessions to generate score distributions." />
            </div>
          ) : (
            <div className="h-64 w-full flex items-center justify-center">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={scoreDistribution}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={85}
                    paddingAngle={4}
                    dataKey="count"
                    nameKey="range"
                  >
                    {scoreDistribution.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.fill} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#ffffff',
                      borderColor: '#e2e8f0',
                      borderRadius: '0.5rem',
                      fontSize: '12px',
                    }}
                    formatter={(value, name) => [`${value} Drivers`, name]}
                  />
                  <Legend
                    verticalAlign="bottom"
                    height={36}
                    iconType="circle"
                    wrapperStyle={{ fontSize: '11px', color: '#64748b' }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>
      </div>

      {/* Row 2: Fleet Performance Summary & Real Telemetry Insights */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Top Safety Performers */}
        <Card
          title="Fleet Safety Leaderboard"
          subtitle="Ranked driver performance based on cumulative road hours and incident ratings"
        >
          {topDrivers.length === 0 ? (
            <div className="py-8 text-center text-xs text-slate-500">
              No registered drivers available to rank.
            </div>
          ) : (
            <div className="space-y-3">
              {topDrivers.map((driver, index) => (
                <div
                  key={driver.driver_id}
                  className="flex items-center justify-between p-3 rounded-xl bg-slate-50 border border-slate-200/80 text-xs"
                >
                  <div className="flex items-center gap-3">
                    <div className={`w-7 h-7 rounded-lg flex items-center justify-center font-bold text-xs ${
                      index === 0 ? 'bg-amber-100 text-amber-800' : index === 1 ? 'bg-slate-200 text-slate-700' : 'bg-orange-100 text-orange-800'
                    }`}>
                      #{index + 1}
                    </div>
                    <div>
                      <span className="font-bold text-slate-900 block">{driver.name}</span>
                      <span className="text-slate-500 text-[11px]">
                        {driver.driving_hours ? `${driver.driving_hours} road hours` : '0 road hours'} • {driver.total_trips || 0} shifts
                      </span>
                    </div>
                  </div>

                  <div className="text-right">
                    <span className="font-mono font-bold text-emerald-600 text-sm block">
                      {driver.safety_score !== null && driver.safety_score !== undefined ? `${driver.safety_score}%` : '100%'}
                    </span>
                    <span className="text-[10px] text-slate-400">Safety Rating</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* Safety Officer Insights */}
        <Card
          title="Fleet Operations Summary"
          subtitle="Automated safety evaluation derived from database telemetry"
        >
          <div className="space-y-3 text-xs">
            <div className="p-3.5 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-900">
              <span className="font-bold block text-sm flex items-center gap-1.5">
                <ShieldCheck className="w-4 h-4 text-emerald-600" />
                Fleet Benchmark Rating
              </span>
              <p className="mt-1 text-emerald-800">
                Average fleet safety index is currently <strong className="font-semibold">{metrics?.average_safety_score || 95.0}%</strong> across {metrics?.total_drivers || drivers.length} enrolled commercial drivers.
              </p>
            </div>

            <div className="p-3.5 rounded-xl bg-blue-50 border border-blue-200 text-blue-900">
              <span className="font-bold block text-sm flex items-center gap-1.5">
                <Users className="w-4 h-4 text-blue-600" />
                Incident Breakdown
              </span>
              <p className="mt-1 text-blue-800">
                Recorded telemetry contains {metrics?.critical_incidents || 0} Level-3 critical events, {metrics?.warning_incidents || 0} Level-2 warning alerts, and {metrics?.nudge_incidents || 0} Level-1 caution events.
              </p>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
