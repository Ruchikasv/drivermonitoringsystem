import { apiClient } from './api';
import { MOCK_ALERTS } from '../mock/mockAlerts';

export const alertService = {
  async getAlerts(filters = {}) {
    try {
      const response = await apiClient.get('/alerts', { params: filters });
      return response.data;
    } catch {
      let alerts = [...MOCK_ALERTS];

      if (filters.level && filters.level !== 'ALL') {
        alerts = alerts.filter((a) => a.level === Number(filters.level));
      }
      if (filters.driver_id && filters.driver_id !== 'ALL') {
        alerts = alerts.filter((a) => a.driver_id === Number(filters.driver_id));
      }
      if (filters.search) {
        const query = filters.search.toLowerCase();
        alerts = alerts.filter(
          (a) =>
            a.driver_name.toLowerCase().includes(query) ||
            a.event_type.toLowerCase().includes(query) ||
            a.vehicle_plate.toLowerCase().includes(query)
        );
      }

      return alerts;
    }
  },

  async getRecentAlerts(limit = 5) {
    const alerts = await this.getAlerts();
    return alerts.slice(0, limit);
  }
};
