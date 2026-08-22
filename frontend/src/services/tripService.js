import { apiClient } from './api';
import { MOCK_TRIPS } from '../mock/mockTrips';

export const tripService = {
  async getTrips(filters = {}) {
    try {
      const response = await apiClient.get('/trips', { params: filters });
      return response.data;
    } catch {
      let trips = [...MOCK_TRIPS];

      if (filters.status && filters.status !== 'ALL') {
        trips = trips.filter((t) => t.status === filters.status);
      }
      if (filters.driver_id && filters.driver_id !== 'ALL') {
        trips = trips.filter((t) => t.driver_id === Number(filters.driver_id));
      }
      if (filters.search) {
        const query = filters.search.toLowerCase();
        trips = trips.filter(
          (t) =>
            t.trip_id.toLowerCase().includes(query) ||
            t.driver_name.toLowerCase().includes(query) ||
            t.origin.toLowerCase().includes(query) ||
            t.destination.toLowerCase().includes(query)
        );
      }

      return trips;
    }
  },

  async getRecentTrips(limit = 5) {
    const trips = await this.getTrips();
    return trips.slice(0, limit);
  }
};
