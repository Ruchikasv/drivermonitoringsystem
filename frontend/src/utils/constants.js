/**
 * Fleet & Driver Monitoring System Constants
 */

export const ALERT_LEVELS = {
  LEVEL_1: {
    id: 1,
    name: 'Level 1',
    label: 'Low Warning',
    color: 'text-amber-700 bg-amber-50 border-amber-200',
    badgeClass: 'bg-amber-100 text-amber-800 border-amber-300',
    description: 'Minor distraction or momentary closure (<1.0s)',
  },
  LEVEL_2: {
    id: 2,
    name: 'Level 2',
    label: 'Moderate Alert',
    color: 'text-orange-700 bg-orange-50 border-orange-200',
    badgeClass: 'bg-orange-100 text-orange-800 border-orange-300',
    description: 'Prolonged eye closure or yawning pattern (1.0s - 2.5s)',
  },
  LEVEL_3: {
    id: 3,
    name: 'Level 3',
    label: 'Critical Hazard',
    color: 'text-red-700 bg-red-50 border-red-200',
    badgeClass: 'bg-red-100 text-red-800 border-red-300',
    description: 'Severe microsleep (>2.5s) or alcohol sensor trigger',
  },
};

export const DRIVER_STATUS = {
  ON_ROUTE: {
    id: 'ON_ROUTE',
    label: 'Active on Route',
    badgeClass: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    dotClass: 'bg-emerald-500',
  },
  ACTIVE: {
    id: 'ACTIVE',
    label: 'Active on Route',
    badgeClass: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    dotClass: 'bg-emerald-500',
  },
  RESTING: {
    id: 'RESTING',
    label: 'On Break',
    badgeClass: 'bg-blue-50 text-blue-700 border-blue-200',
    dotClass: 'bg-blue-500',
  },
  OFF_DUTY: {
    id: 'OFF_DUTY',
    label: 'Off Duty',
    badgeClass: 'bg-slate-100 text-slate-600 border-slate-200',
    dotClass: 'bg-slate-400',
  },
  SUSPENDED: {
    id: 'SUSPENDED',
    label: 'Safety Hold',
    badgeClass: 'bg-red-50 text-red-700 border-red-200',
    dotClass: 'bg-red-500',
  },
};

export const TELEMETRY_THRESHOLDS = {
  EAR_NORMAL: 0.28,
  EAR_DROWSY_THRESHOLD: 0.20,
  MAR_NORMAL: 0.35,
  MAR_YAWN_THRESHOLD: 0.65,
  PERCLOS_THRESHOLD_PCT: 15.0,
};
