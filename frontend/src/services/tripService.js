import { apiClient } from './api';

export const tripService = {
  async getTrips(filters = {}) {
    const response = await apiClient.get('/trips', { params: filters });
    return response.data || [];
  },

  async getRecentTrips(limit = 5) {
    const trips = await this.getTrips();
    return trips.slice(0, limit);
  }
};

