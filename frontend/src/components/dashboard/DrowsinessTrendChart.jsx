import React from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';

export default function DrowsinessTrendChart({ data = [] }) {
  const hasData = data && data.length > 0 && data.some((d) => (d.critical || d.warning || d.nudge));

  if (!hasData) {
    return (
      <div className="h-64 w-full flex flex-col items-center justify-center text-center p-6 bg-slate-50/50 rounded-xl border border-slate-100">
        <p className="text-xs font-semibold text-slate-600">No Incident History in the Last 7 Days</p>
        <p className="text-[11px] text-slate-400 mt-1 max-w-sm">
          Real-time safety events logged during driver monitoring shifts will be graphed here automatically.
        </p>
      </div>
    );
  }

  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
          <XAxis
            dataKey="day"
            tick={{ fontSize: 11, fill: '#64748b' }}
            axisLine={{ stroke: '#e2e8f0' }}
            tickLine={false}
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
            formatter={(value, name) => [`${value} Events`, name === 'critical' ? 'Level 3 Critical' : name === 'warning' ? 'Level 2 Warning' : 'Level 1 Nudge']}
            labelFormatter={(label) => `Day: ${label}`}
          />
          <Legend
            verticalAlign="top"
            align="right"
            height={28}
            iconType="circle"
            wrapperStyle={{ fontSize: '11px', color: '#64748b' }}
          />
          <Bar dataKey="critical" name="Critical (L3)" fill="#ef4444" stackId="a" radius={[0, 0, 0, 0]} />
          <Bar dataKey="warning" name="Warning (L2)" fill="#f59e0b" stackId="a" radius={[0, 0, 0, 0]} />
          <Bar dataKey="nudge" name="Caution (L1)" fill="#3b82f6" stackId="a" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

