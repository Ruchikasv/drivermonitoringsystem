import { apiClient } from './api';

/**
 * Service for MQ-3 alcohol sensor telemetry and safety lockout.
 */
export const alcoholService = {
  /**
   * Retrieve live MQ-3 connection, state machine phase, and lockout status.
   */
  async getAlcoholStatus(sessionId = null) {
    const params = sessionId ? { session_id: sessionId } : {};
    const res = await apiClient.get('/api/alcohol/status', { params });
    return res.data;
  },

  /**
   * Driver prototype alarm acknowledgement (silences audio).
   * Does NOT unlock the vehicle.
   */
  async acknowledgeAlarm(sessionId = null) {
    const res = await apiClient.post('/api/alcohol/acknowledge', { session_id: sessionId });
    return res.data;
  },

  /**
   * Authorized fleet owner resolves the lockout with recorded reason.
   */
  async resolveLockout(reason, incidentId = null) {
    const res = await apiClient.post('/api/alcohol/resolve', {
      reason,
      incident_id: incidentId,
    });
    return res.data;
  },
};
