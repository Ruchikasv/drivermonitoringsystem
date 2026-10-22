import { apiClient } from './api';

export const incidentService = {
  /**
   * List all drowsiness/alert incidents.
   */
  async getIncidents(limit = 200) {
    const response = await apiClient.get('/incidents/', { params: { limit } });
    return response.data;
  },

  /**
   * Get incidents for a specific driver.
   */
  async getDriverIncidents(driverId) {
    const response = await apiClient.get(`/incidents/driver/${driverId}`);
    return response.data;
  },

  /**
   * Get safety rating for a driver.
   */
  async getDriverRating(driverId) {
    const response = await apiClient.get(`/incidents/driver/${driverId}/rating`);
    return response.data;
  },

  /**
   * Delete evidence screenshot and clear DB path.
   */
  async deleteEvidence(incidentId) {
    const response = await apiClient.delete(`/incidents/${incidentId}/evidence`);
    return response.data;
  },

  /**
   * Fetch evidence screenshot as an authenticated Blob and return Object URL.
   * Console logging is intentional for end-to-end demo verification.
   */
  async fetchEvidenceBlob(incidentId, type = 'primary') {
    const query = type && type !== 'primary' ? `?type=${type}` : '';
    console.log(`[EvidenceService] Fetching evidence for incident #${incidentId} (${type}) via GET /incidents/${incidentId}/evidence${query}`);
    try {
      const response = await apiClient.get(`/incidents/${incidentId}/evidence${query}`, {
        responseType: 'blob',
      });
      console.log(`[EvidenceService] ✅ Evidence received for incident #${incidentId}: status=${response.status}, type=${response.data?.type}, size=${response.data?.size}b`);
      return URL.createObjectURL(response.data);
    } catch (err) {
      const status = err.response?.status;
      const detail = err.response?.data?.detail || err.message;
      console.error(`[EvidenceService] ❌ Evidence fetch FAILED for incident #${incidentId} (${type}): HTTP ${status} — ${detail}`);
      throw err;
    }
  },

  /**
   * Get direct URL to evidence screenshot JPEG with auth token query param for <img> elements.
   */
  getEvidenceUrl(incidentId, type = 'primary') {
    const base = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';
    const token = localStorage.getItem('token');
    const tokenParam = token ? `token=${encodeURIComponent(token)}` : '';
    const typeParam = type && type !== 'primary' ? `type=${type}` : '';
    const params = [typeParam, tokenParam].filter(Boolean).join('&');
    const query = params ? `?${params}` : '';
    return `${base}/incidents/${incidentId}/evidence${query}`;
  },
};

