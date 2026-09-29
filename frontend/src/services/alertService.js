import { apiClient } from './api';

export const alertService = {
  async getAlerts(filters = {}) {
    const response = await apiClient.get('/alerts', { params: filters });
    return response.data || [];
  },

  async getRecentAlerts(limit = 10) {
    const response = await apiClient.get('/alerts', { params: { limit } });
    return response.data || [];
  }
};

