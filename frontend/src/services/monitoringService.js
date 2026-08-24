import { apiClient } from './api';

export const monitoringService = {
  /**
   * Create an active monitoring session for a driver and vehicle.
   */
  async createSession(driverId, vehicleId) {
    const response = await apiClient.post('/sessions/', {
      driver_id: driverId,
      vehicle_id: vehicleId,
    });
    return response.data;
  },

  /**
   * Get all active sessions (for Owner Portal dashboard).
   */
  async getActiveSessions() {
    const response = await apiClient.get('/sessions/active');
    return response.data;
  },

  /**
   * Get single session details.
   */
  async getSession(sessionId) {
    const response = await apiClient.get(`/sessions/${sessionId}`);
    return response.data;
  },

  /**
   * End a monitoring session (driver finished trip).
   */
  async endSession(sessionId) {
    const response = await apiClient.delete(`/sessions/${sessionId}`);
    return response.data;
  },

  /**
   * Get in-memory live metrics for all streaming sessions (for Owner live monitoring).
   */
  async getAllLiveMetrics() {
    const response = await apiClient.get('/sessions/live/all');
    return response.data;
  },

  /**
   * Get in-memory live metrics for a specific session.
   */
  async getSessionLiveMetrics(sessionId) {
    const response = await apiClient.get(`/sessions/${sessionId}/live`);
    return response.data;
  },

  /**
   * Get WebSocket URL for driver real-time stream.
   */
  getWebSocketUrl(sessionId) {
    const base = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000')
      .replace(/^http/, 'ws');
    return `${base}/ws/monitor/${sessionId}`;
  },
};
