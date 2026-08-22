/**
 * Fleet Analytics & Trend Dataset
 * NOTE: All trends below represent synthesized demo preview data.
 */

export const MOCK_DROWSINESS_TREND = [
  { time: '06:00', avgFatigueScore: 12, alertCount: 0 },
  { time: '08:00', avgFatigueScore: 18, alertCount: 0 },
  { time: '10:00', avgFatigueScore: 22, alertCount: 1 },
  { time: '12:00', avgFatigueScore: 35, alertCount: 1 },
  { time: '14:00', avgFatigueScore: 58, alertCount: 3 }, // Post-lunch peak
  { time: '16:00', avgFatigueScore: 42, alertCount: 2 },
  { time: '18:00', avgFatigueScore: 28, alertCount: 1 },
  { time: '20:00', avgFatigueScore: 38, alertCount: 2 },
  { time: '22:00', avgFatigueScore: 65, alertCount: 4 }, // Night shift surge
  { time: '00:00', avgFatigueScore: 72, alertCount: 5 },
  { time: '02:00', avgFatigueScore: 84, alertCount: 7 }, // Peak circadian low
  { time: '04:00', avgFatigueScore: 60, alertCount: 3 },
];

export const MOCK_FLEET_METRICS = {
  totalDrivers: 5,
  activeDrivers: 3,
  todayAlerts: 4,
  fleetSafetyScore: 85.0,
  scoreDelta: '+1.8%',
  totalKilometersToday: 1020,
  averageTripDurationMinutes: 180,
  alcoholIncidents: 0,
  level3Incidents: 1,
};

export const MOCK_ALERTS_BY_DRIVER = [
  { name: 'Pooja Sharma', count: 0, score: 96 },
  { name: 'Anand Kumar', count: 4, score: 88 },
  { name: 'Vikram Singh', count: 8, score: 82 },
  { name: 'Rajesh Nair', count: 11, score: 74 },
];

export const MOCK_SCORE_DISTRIBUTION = [
  { range: '90-100 (Excellent)', count: 1, fill: '#10b981' },
  { range: '80-89 (Good)', count: 2, fill: '#2563eb' },
  { range: '70-79 (Fair)', count: 1, fill: '#f59e0b' },
  { range: '<70 (At Risk)', count: 0, fill: '#ef4444' },
];
