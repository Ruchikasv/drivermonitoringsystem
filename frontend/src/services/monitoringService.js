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
   * Get single session details with optional driver token.
   */
  async getSession(sessionId, token = null) {
    const config = token ? { params: { token } } : {};
    const response = await apiClient.get(`/sessions/${sessionId}`, config);
    return response.data;
  },

  /**
   * Pause a running trip.
   */
  async pauseSession(sessionId, token = null) {
    const config = token ? { params: { token } } : {};
    const response = await apiClient.post(`/sessions/${sessionId}/pause`, null, config);
    return response.data;
  },

  /**
   * Resume a paused trip.
   */
  async resumeSession(sessionId, token = null) {
    const config = token ? { params: { token } } : {};
    const response = await apiClient.post(`/sessions/${sessionId}/resume`, null, config);
    return response.data;
  },

  /**
   * End a monitoring session (driver finished trip).
   */
  async endSession(sessionId, token = null) {
    const config = token ? { params: { token } } : {};
    const response = await apiClient.delete(`/sessions/${sessionId}`, config);
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
   * Get WebSocket URL for driver real-time stream with optional session token.
   */
  getWebSocketUrl(sessionId, token = null) {
    let base = import.meta.env.VITE_API_BASE_URL;
    if (!base && typeof window !== 'undefined' && window.location) {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      base = `${protocol}//${window.location.hostname}:8000`;
    } else {
      base = (base || 'http://127.0.0.1:8000').replace(/^http/, 'ws');
    }
    const url = `${base}/ws/monitor/${sessionId}`;
    return token ? `${url}?token=${encodeURIComponent(token)}` : url;
  },
};
