import { apiClient } from './api';

/**
 * Normalizes driver objects returned from backend to ensure
 * uniform property access across all components.
 */
function normalizeDriver(d) {
  if (!d) return null;
  return {
    ...d,
    status: d.status || 'OFF_DUTY',
    phone: d.phone || null,
    email: d.email || null,
    license_no: d.license_no || null,
    isRegisteredBackend: true,
    vehicle: d.vehicle || null,
    vehicle_plate: d.vehicle ? d.vehicle.registration_number : (d.vehicle_plate || null),
    assigned_vehicle: d.vehicle ? d.vehicle.model : (d.assigned_vehicle || null),
    safety_score: d.safety_score !== undefined ? d.safety_score : null,
    total_trips: d.total_trips !== undefined ? d.total_trips : 0,
    driving_hours: d.driving_hours !== undefined ? d.driving_hours : 0.0,
    drowsiness_events: d.drowsiness_events !== undefined ? d.drowsiness_events : 0,
    alcohol_events: d.alcohol_events !== undefined ? d.alcohol_events : 0,
  };
}

/**
 * Driver Service
 * Communicates directly with backend /drivers endpoints.
 */
export const driverService = {
  /**
   * Fetch all registered drivers
   */
  async getDrivers() {
    const response = await apiClient.get('/drivers');
    const backendRaw = response.data || [];
    return backendRaw.map(normalizeDriver);
  },

  /**
   * Fetch a single driver by ID
   */
  async getDriverById(id) {
    const numericId = Number(id);
    const response = await apiClient.get(`/drivers/${numericId}`);
    return normalizeDriver(response.data);
  },

  /**
   * Update driver profile information (name, phone, email, license_no)
   */
  async updateDriverProfile(id, profileData) {
    const numericId = Number(id);
    const response = await apiClient.put(`/drivers/${numericId}/profile`, profileData);
    return normalizeDriver(response.data);
  },

  /**
   * Fire / Delete a driver completely from fleet registry
   */
  async deleteDriver(id) {
    const numericId = Number(id);
    const response = await apiClient.delete(`/drivers/${numericId}`);
    return response.data;
  },

  /**
   * Fetch active drivers currently on duty
   */
  async getActiveDrivers() {
    const drivers = await this.getDrivers();
    return drivers.filter((d) => d.status === 'ON_ROUTE');
  }
};


