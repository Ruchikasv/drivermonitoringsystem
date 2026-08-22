/**
 * Fleet Drivers Dataset
 *
 * NOTE: Driver ID 1 (Ruchika) is the real driver registered in SQLite.
 * Real profile metadata & vehicle assignment below match the active SQLite database.
 * Additional drivers below are provided for fleet safety UI preview (DEMO DATA).
 */

export const MOCK_DRIVERS = [
  {
    driver_id: 1,
    name: 'Ruchika',
    status: 'ACTIVE',
    phone: '7019453545',
    email: 'svruchika@gmail.com',
    license_no: 'KA69fu6969',
    vehicle_plate: 'KA-01-MJ-8821',
    assigned_vehicle: 'Tata Prima 4028.S',
    vehicle: {
      vehicle_id: 2,
      registration_number: 'KA-01-MJ-8821',
      model: 'Tata Prima 4028.S',
      vehicle_type: 'Heavy Haul',
      assigned_at: '2026-08-22T19:35:31.008891+00:00',
    },
    safety_score: null,
    total_trips: null,
    driving_hours: null,
    drowsiness_events: null,
    alcohol_events: null,
    created_at: '2026-08-22T17:44:41.378309+00:00',
    isRegisteredBackend: true, // Corresponds directly to SQLite drivers.db
    current_trip: null,
  },
  {
    driver_id: 2,
    name: 'Vikram Singh',
    status: 'ACTIVE',
    vehicle_plate: 'KA-04-E-4412',
    assigned_vehicle: 'Ashok Leyland 2820 (Cargo)',
    phone: '+91 98210 99412',
    email: 'vikram.s@fleetsafety.internal',
    license_no: 'DL-KA042021009182',
    safety_score: 82,
    total_trips: 64,
    driving_hours: 284.0,
    drowsiness_events: 7,
    alcohol_events: 0,
    created_at: '2026-06-15T09:12:00Z',
    isRegisteredBackend: false,
    current_trip: {
      trip_id: 'TRP-1043',
      route: 'Hosur Logistics Park ➔ Electronic City',
      start_time: '2026-08-22T16:30:00Z',
      duration_minutes: 105,
      drowsiness_status: 'ATTENTION_NEEDED',
      alcohol_status: 'CLEARED',
    }
  },
  {
    driver_id: 3,
    name: 'Anand Kumar',
    status: 'RESTING',
    vehicle_plate: 'KA-51-AB-1904',
    assigned_vehicle: 'BharatBenz 3528C (Tipper)',
    phone: '+91 97401 55219',
    email: 'anand.k@fleetsafety.internal',
    license_no: 'DL-KA512022003891',
    safety_score: 88,
    total_trips: 51,
    driving_hours: 198.2,
    drowsiness_events: 4,
    alcohol_events: 0,
    created_at: '2026-05-10T11:40:00Z',
    isRegisteredBackend: false,
    current_trip: null
  },
  {
    driver_id: 4,
    name: 'Rajesh Nair',
    status: 'OFF_DUTY',
    vehicle_plate: 'KA-03-AA-9081',
    assigned_vehicle: 'Eicher Pro 3019 (Tanker)',
    phone: '+91 96112 40012',
    email: 'rajesh.n@fleetsafety.internal',
    license_no: 'DL-KA032020001928',
    safety_score: 74,
    total_trips: 45,
    driving_hours: 176.0,
    drowsiness_events: 11,
    alcohol_events: 1,
    created_at: '2026-04-18T08:00:00Z',
    isRegisteredBackend: false,
    current_trip: null
  },
  {
    driver_id: 5,
    name: 'Pooja Sharma',
    status: 'ACTIVE',
    vehicle_plate: 'KA-53-M-3329',
    assigned_vehicle: 'Tata Signa 4825.TK',
    phone: '+91 98801 88129',
    email: 'pooja.s@fleetsafety.internal',
    license_no: 'DL-KA532023008912',
    safety_score: 96,
    total_trips: 29,
    driving_hours: 112.4,
    drowsiness_events: 1,
    alcohol_events: 0,
    created_at: '2026-07-02T13:20:00Z',
    isRegisteredBackend: false,
    current_trip: {
      trip_id: 'TRP-1044',
      route: 'Nelamangala ➔ Peenya Industrial Area',
      start_time: '2026-08-22T17:00:00Z',
      duration_minutes: 75,
      drowsiness_status: 'NORMAL',
      alcohol_status: 'CLEARED',
    }
  }
];
