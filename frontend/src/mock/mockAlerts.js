/**
 * Fleet Safety Alerts Dataset
 * Categorized by Level 1 (Low), Level 2 (Moderate), Level 3 (Critical)
 * NOTE: All safety alerts below represent simulated events for UI preview.
 * Real registered driver Ruchika currently has no real safety incidents logged.
 */

export const MOCK_ALERTS = [
  {
    alert_id: 'ALT-901',
    driver_id: 2,
    driver_name: 'Vikram Singh',
    vehicle_plate: 'KA-04-E-4412',
    level: 2,
    event_type: 'Frequent Yawning (MAR: 0.72)',
    timestamp: '2026-08-22T17:18:22Z',
    status: 'ACKNOWLEDGED',
    notes: 'In-cabin auditory chime dispatched. Driver alerted.',
    location: 'NH 44, km 38 (Hosur Bypass)'
  },
  {
    alert_id: 'ALT-902',
    driver_id: 4,
    driver_name: 'Rajesh Nair',
    vehicle_plate: 'KA-03-AA-9081',
    level: 3,
    event_type: 'Prolonged Eye Closure (>2.8s microsleep)',
    timestamp: '2026-08-22T15:42:10Z',
    status: 'FLAGGED',
    notes: 'Critical Level 3 alert triggered. Recommended immediate rest stop.',
    location: 'Tumkur Road Toll Plaza'
  },
  {
    alert_id: 'ALT-903',
    driver_id: 2,
    driver_name: 'Vikram Singh',
    vehicle_plate: 'KA-04-E-4412',
    level: 1,
    event_type: 'Head Pitch Deviation (Distraction >3s)',
    timestamp: '2026-08-22T14:55:04Z',
    status: 'RESOLVED',
    notes: 'Driver glanced away from forward road. Self-corrected within 3s.',
    location: 'Bangalore-Tirupati Highway'
  },
  {
    alert_id: 'ALT-904',
    driver_id: 3,
    driver_name: 'Anand Kumar',
    vehicle_plate: 'KA-51-AB-1904',
    level: 1,
    event_type: 'Eye Aspect Ratio Drop (EAR: 0.19)',
    timestamp: '2026-08-22T11:20:15Z',
    status: 'RESOLVED',
    notes: 'Momentary drowsiness detected before scheduled rest interval.',
    location: 'Nice Ring Road, Exit 4'
  },
  {
    alert_id: 'ALT-905',
    driver_id: 2,
    driver_name: 'Vikram Singh',
    vehicle_plate: 'KA-04-E-4412',
    level: 2,
    event_type: 'Elevated PERCLOS (18.4% eyelid closure rate)',
    timestamp: '2026-08-21T21:10:45Z',
    status: 'RESOLVED',
    notes: 'Night shift fatigue pattern detected.',
    location: 'Kolar Industrial Area'
  }
];
