import { apiClient } from './api';

export const analyticsService = {
  async getFleetMetrics() {
    const response = await apiClient.get('/analytics/metrics');
    return response.data;
  },

  async getDrowsinessTrend() {
    const response = await apiClient.get('/analytics/drowsiness-trend');
    return response.data || [];
  },

  async getAlertsByDriver() {
    const response = await apiClient.get('/analytics/alerts-by-driver');
    return response.data || [];
  },

  async getScoreDistribution() {
    const response = await apiClient.get('/analytics/score-distribution');
    return response.data || [];
  }
};

