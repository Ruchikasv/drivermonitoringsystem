import React from 'react';
import { getSafetyScoreCategory } from '../../utils/formatters';

export default function SafetyScore({ score, size = 'md', showCategory = true }) {
  if (score === null || score === undefined) {
    if (size === 'lg') {
      return (
        <div className="flex flex-col items-center">
          <div className="text-3xl font-bold text-slate-400">—</div>
          <span className="text-xs font-medium text-slate-400 mt-1">Awaiting Phase 2 data</span>
        </div>
      );
    }
    return (
      <div className="flex items-center gap-2 text-slate-400">
        <span className="font-bold text-slate-400 text-sm">—</span>
        {showCategory && <span className="text-xs text-slate-400 italic">Awaiting Phase 2</span>}
      </div>
    );
  }

  const category = getSafetyScoreCategory(score);

  if (size === 'sm') {
    return (
      <div className="flex items-center gap-2">
        <span className="font-semibold text-slate-900 text-sm">{score}</span>
        <div className="w-16 h-1.5 bg-slate-100 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full ${category.bg}`}
            style={{ width: `${Math.min(Math.max(score, 0), 100)}%` }}
          />
        </div>
      </div>
    );
  }

  if (size === 'lg') {
    return (
      <div className="flex flex-col items-center">
        <div className="relative flex items-center justify-center">
          <span className="text-4xl font-extrabold text-slate-900">{score}</span>
          <span className="text-sm text-slate-400 font-medium ml-0.5">/100</span>
        </div>
        {showCategory && (
          <span className={`text-xs font-semibold mt-1 px-2.5 py-0.5 rounded-full bg-slate-100 ${category.color}`}>
            {category.label}
          </span>
        )}
      </div>
    );
  }

  // Medium (default)
  return (
    <div className="flex items-center gap-3">
      <span className="font-bold text-slate-900 text-base">{score}</span>
      <div className="flex-1 min-w-[70px] max-w-[100px] h-2 bg-slate-100 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full ${category.bg}`}
          style={{ width: `${Math.min(Math.max(score, 0), 100)}%` }}
        />
      </div>
      {showCategory && (
        <span className={`text-xs font-medium ${category.color}`}>
          {category.label}
        </span>
      )}
    </div>
  );
}
