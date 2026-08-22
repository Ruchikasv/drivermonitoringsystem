import { apiClient } from './api';
import {
  MOCK_DROWSINESS_TREND,
  MOCK_FLEET_METRICS,
  MOCK_ALERTS_BY_DRIVER,
  MOCK_SCORE_DISTRIBUTION
} from '../mock/mockAnalytics';

export const analyticsService = {
  async getFleetMetrics() {
    try {
      const response = await apiClient.get('/analytics/metrics');
      return response.data;
    } catch {
      return MOCK_FLEET_METRICS;
    }
  },

  async getDrowsinessTrend() {
    try {
      const response = await apiClient.get('/analytics/drowsiness-trend');
      return response.data;
    } catch {
      return MOCK_DROWSINESS_TREND;
    }
  },

  async getAlertsByDriver() {
    try {
      const response = await apiClient.get('/analytics/alerts-by-driver');
      return response.data;
    } catch {
      return MOCK_ALERTS_BY_DRIVER;
    }
  },

  async getScoreDistribution() {
    try {
      const response = await apiClient.get('/analytics/score-distribution');
      return response.data;
    } catch {
      return MOCK_SCORE_DISTRIBUTION;
    }
  }
};
