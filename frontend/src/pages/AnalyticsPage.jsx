import React, { useState, useEffect } from 'react';
import Card from '../components/common/Card';
import LoadingState from '../components/common/LoadingState';
import ErrorState from '../components/common/ErrorState';
import { analyticsService } from '../services/analyticsService';
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
import { BarChart3, TrendingUp, ShieldAlert, Award, Clock, Coffee } from 'lucide-react';

const BREAK_PATTERN_DATA = [
  { interval: '0-2 hrs', compliance: 98 },
  { interval: '2-4 hrs', compliance: 86 },
  { interval: '4-6 hrs', compliance: 62 },
  { interval: '>6 hrs (Overtime)', compliance: 24 },
];

export default function AnalyticsPage() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [alertsByDriver, setAlertsByDriver] = useState([]);
  const [scoreDistribution, setScoreDistribution] = useState([]);

  const loadAnalytics = async () => {
    try {
      setLoading(true);
      setError(null);
      const [alerts, scores] = await Promise.all([
        analyticsService.getAlertsByDriver(),
        analyticsService.getScoreDistribution(),
      ]);
      setAlertsByDriver(alerts);
      setScoreDistribution(scores);
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

  return (
    <div className="space-y-6">
      {/* 2 Column Charts: Alerts by Driver & Safety Score Distribution */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Alerts by Driver Bar Chart */}
        <Card
          title="Safety Infractions by Driver"
          subtitle="Total recorded Level 1-3 fatigue & distraction incidents"
        >
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
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#ffffff',
                    borderColor: '#e2e8f0',
                    borderRadius: '0.5rem',
                    boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)',
                    fontSize: '12px',
                  }}
                  formatter={(value) => [`${value} Alerts`, 'Infractions']}
                />
                <Bar dataKey="count" fill="#2563eb" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        {/* Safety Score Distribution Donut */}
        <Card
          title="Fleet Safety Rating Distribution"
          subtitle="Commercial driver score breakdown across benchmark tiers"
        >
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
        </Card>
      </div>

      {/* Row 2: Break Patterns & Compliance */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Mandatory Break Compliance */}
        <Card
          title="Mandatory Break Compliance"
          subtitle="Driver rest interval adherence across continuous driving blocks"
        >
          <div className="space-y-4">
            {BREAK_PATTERN_DATA.map((item) => (
              <div key={item.interval} className="space-y-1.5">
                <div className="flex items-center justify-between text-xs">
                  <span className="font-semibold text-slate-700 flex items-center gap-1.5">
                    <Coffee className="w-3.5 h-3.5 text-slate-400" />
                    Driving Window: {item.interval}
                  </span>
                  <span className="font-mono font-bold text-slate-900">{item.compliance}%</span>
                </div>
                <div className="h-2 w-full bg-slate-100 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all ${
                      item.compliance >= 80
                        ? 'bg-emerald-500'
                        : item.compliance >= 60
                        ? 'bg-amber-500'
                        : 'bg-red-500'
                    }`}
                    style={{ width: `${item.compliance}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </Card>

        {/* Analytics Summary Insights */}
        <Card
          title="Safety Officer Insights"
          subtitle="Automated recommendations based on fleet telemetry"
        >
          <div className="space-y-3 text-xs">
            <div className="p-3 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-900">
              <span className="font-bold block text-sm">✓ Top Performer</span>
              <p className="mt-0.5 text-emerald-800">
                Pooja Sharma and Ruchika have maintained &gt;94% safety scores with zero Level-3 events over the last 30 operational days.
              </p>
            </div>

            <div className="p-3 rounded-lg bg-amber-50 border border-amber-200 text-amber-900">
              <span className="font-bold block text-sm">⚠ Fatigue Alert Window</span>
              <p className="mt-0.5 text-amber-800">
                Circadian fatigue peaks sharply between 02:00 AM and 04:00 AM. Route planners should schedule compulsory 20-minute rest halts during night shifts.
              </p>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
