import { apiClient } from './api';

export const authService = {
  /**
   * Register a new driver via facial capture frames.
   * @param {Object} payload - { name, phone, email, license_no, frames_b64 }
   */
  async registerDriver(payload) {
    const response = await apiClient.post('/auth/register', payload);
    return response.data;
  },

  /**
   * Authenticate a driver using a single webcam frame.
   * @param {string} frameB64 - Base64 encoded JPEG
   */
  async authenticateDriver(frameB64) {
    const response = await apiClient.post('/auth/authenticate', { frame_b64: frameB64 });
    return response.data;
  },
};
