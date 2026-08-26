import { apiClient } from './api';

export const alertService = {
  async getAlerts(filters = {}) {
    const response = await apiClient.get('/alerts', { params: filters });
    return response.data || [];
  },

  async getRecentAlerts(limit = 5) {
    const alerts = await this.getAlerts();
    return alerts.slice(0, limit);
  }
};

