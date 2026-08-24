import { apiClient } from './api';

export const vehicleService = {
  /**
   * Fetch all vehicles with assignment metadata
   */
  async getVehicles() {
    const response = await apiClient.get('/vehicles');
    return response.data;
  },

  /**
   * Create a new vehicle
   */
  async createVehicle(vehicleData) {
    const response = await apiClient.post('/vehicles', vehicleData);
    return response.data;
  },

  /**
   * Update an existing vehicle's specifications
   */
  async updateVehicle(vehicleId, vehicleData) {
    const response = await apiClient.put(`/vehicles/${vehicleId}`, vehicleData);
    return response.data;
  },

  /**
   * Delete an available vehicle
   */
  async deleteVehicle(vehicleId) {
    const response = await apiClient.delete(`/vehicles/${vehicleId}`);
    return response.data;
  },

  /**
   * Assign a vehicle to a driver
   */
  async assignVehicle(driverId, vehicleId) {
    const response = await apiClient.post(`/drivers/${driverId}/vehicle`, {
      vehicle_id: vehicleId,
    });
    return response.data;
  },

  /**
   * Unassign a vehicle from a driver
   */
  async unassignVehicle(driverId) {
    const response = await apiClient.delete(`/drivers/${driverId}/vehicle`);
    return response.data;
  },
};
