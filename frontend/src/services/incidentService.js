import { apiClient } from './api';

export const incidentService = {
  /**
   * List all drowsiness/alert incidents.
   */
  async getIncidents(limit = 200) {
    const response = await apiClient.get('/incidents/', { params: { limit } });
    return response.data;
  },

  /**
   * Get incidents for a specific driver.
   */
  async getDriverIncidents(driverId) {
    const response = await apiClient.get(`/incidents/driver/${driverId}`);
    return response.data;
  },

  /**
   * Get safety rating for a driver.
   */
  async getDriverRating(driverId) {
    const response = await apiClient.get(`/incidents/driver/${driverId}/rating`);
    return response.data;
  },

  /**
   * Delete evidence screenshot and clear DB path.
   */
  async deleteEvidence(incidentId) {
    const response = await apiClient.delete(`/incidents/${incidentId}/evidence`);
    return response.data;
  },

  /**
   * Get direct URL to evidence screenshot JPEG.
   */
  getEvidenceUrl(incidentId) {
    const base = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';
    return `${base}/incidents/${incidentId}/evidence`;
  },
};

