import { apiClient } from './api';
import { MOCK_DRIVERS } from '../mock/mockDrivers';

// Local in-memory driver store for frontend session fallback
let localDriversStore = [...MOCK_DRIVERS];

/**
 * Normalizes driver objects returned from backend or mock store to ensure
 * uniform property access across all components.
 */
function normalizeDriver(d) {
  if (!d) return null;
  return {
    ...d,
    status: d.status || 'ACTIVE',
    phone: d.phone || null,
    email: d.email || null,
    license_no: d.license_no || null,
    isRegisteredBackend: Boolean(d.isRegisteredBackend),
    vehicle: d.vehicle || null,
    vehicle_plate: d.vehicle ? d.vehicle.registration_number : (d.vehicle_plate || null),
    assigned_vehicle: d.vehicle ? d.vehicle.model : (d.assigned_vehicle || null),
    safety_score: d.safety_score !== undefined ? d.safety_score : null,
    total_trips: d.total_trips !== undefined ? d.total_trips : null,
    driving_hours: d.driving_hours !== undefined ? d.driving_hours : null,
    drowsiness_events: d.drowsiness_events !== undefined ? d.drowsiness_events : null,
    alcohol_events: d.alcohol_events !== undefined ? d.alcohol_events : null,
  };
}

/**
 * Driver Service
 * Fetches real registered drivers from backend when active, and combines with demo drivers.
 */
export const driverService = {
  /**
   * Fetch all drivers (combining real backend drivers + remaining demo drivers)
   */
  async getDrivers() {
    try {
      const response = await apiClient.get('/drivers');
      const backendRaw = response.data || [];
      const backendDrivers = backendRaw.map(normalizeDriver);

      // Filter out mock drivers that match real backend driver IDs
      const backendIds = new Set(backendDrivers.map((d) => d.driver_id));
      const demoDrivers = localDriversStore
        .filter((d) => !backendIds.has(d.driver_id) && !d.isRegisteredBackend)
        .map(normalizeDriver);

      return [...backendDrivers, ...demoDrivers];
    } catch {
      return localDriversStore.map(normalizeDriver);
    }
  },

  /**
   * Fetch a single driver by ID
   */
  async getDriverById(id) {
    const numericId = Number(id);
    try {
      const response = await apiClient.get(`/drivers/${numericId}`);
      return normalizeDriver(response.data);
    } catch {
      const found = localDriversStore.find((d) => d.driver_id === numericId);
      return normalizeDriver(found) || null;
    }
  },

  /**
   * Update driver profile information (name, phone, email, license_no)
   */
  async updateDriverProfile(id, profileData) {
    const numericId = Number(id);
    try {
      const response = await apiClient.put(`/drivers/${numericId}/profile`, profileData);
      return normalizeDriver(response.data);
    } catch {
      // Local fallback update
      localDriversStore = localDriversStore.map((d) => {
        if (d.driver_id === numericId) {
          return {
            ...d,
            name: profileData.name !== undefined ? profileData.name : d.name,
            phone: profileData.phone !== undefined ? profileData.phone : d.phone,
            email: profileData.email !== undefined ? profileData.email : d.email,
            license_no: profileData.license_no !== undefined ? profileData.license_no : d.license_no,
          };
        }
        return d;
      });

      const found = localDriversStore.find((d) => d.driver_id === numericId);
      return normalizeDriver(found) || null;
    }
  },

  /**
   * Fetch active drivers currently on duty
   */
  async getActiveDrivers() {
    const drivers = await this.getDrivers();
    return drivers.filter((d) => d.status === 'ACTIVE' || d.status === undefined || d.isRegisteredBackend);
  }
};
