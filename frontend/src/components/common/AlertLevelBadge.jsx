import React from 'react';
import { ALERT_LEVELS } from '../../utils/constants';

export default function AlertLevelBadge({ level, showLabel = true }) {
  const key = `LEVEL_${level}`;
  const config = ALERT_LEVELS[key] || {
    label: `Level ${level}`,
    badgeClass: 'bg-slate-100 text-slate-700 border-slate-300',
  };

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-md text-xs font-semibold border ${config.badgeClass}`}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-current opacity-80" />
      <span>{config.name || `Level ${level}`}</span>
      {showLabel && <span className="opacity-75 font-normal">({config.label})</span>}
    </span>
  );
}
