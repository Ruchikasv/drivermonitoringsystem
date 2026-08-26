import { apiClient } from './api';

/**
 * Service for Fleet Owner / Manager Authentication
 */
export const authService = {
  /**
   * Fetch total registered fleet operators count.
   */
  async getRegisteredOwnersCount() {
    const res = await apiClient.get('/owner/auth/count');
    return res.data?.count ?? 0;
  },

  /**
   * Register a new fleet owner account.
   */
  async register(name, email, password) {
    const res = await apiClient.post('/owner/auth/register', { name, email, password });
    if (res.data?.token) {
      localStorage.setItem('dms_owner_token', res.data.token);
      localStorage.setItem(
        'dms_owner_profile',
        JSON.stringify({ owner_id: res.data.owner_id, name: res.data.name, email: res.data.email })
      );
    }
    return res.data;
  },

  /**
   * Log in an existing fleet owner.
   */
  async login(email, password) {
    const res = await apiClient.post('/owner/auth/login', { email, password });
    if (res.data?.token) {
      localStorage.setItem('dms_owner_token', res.data.token);
      localStorage.setItem(
        'dms_owner_profile',
        JSON.stringify({ owner_id: res.data.owner_id, name: res.data.name, email: res.data.email })
      );
    }
    return res.data;
  },

  /**
   * Log out the current owner and invalidate the session cookie.
   */
  async logout() {
    try {
      await apiClient.post('/owner/auth/logout');
    } catch {
      // Ignore network errors during logout
    } finally {
      localStorage.removeItem('dms_owner_token');
      localStorage.removeItem('dms_owner_profile');
    }
  },

  /**
   * Fetch current authenticated owner profile.
   */
  async getProfile() {
    const res = await apiClient.get('/owner/auth/me');
    if (res.data) {
      localStorage.setItem('dms_owner_profile', JSON.stringify(res.data));
    }
    return res.data;
  },

  /**
   * Get cached owner profile from local storage.
   */
  getCachedProfile() {
    try {
      const data = localStorage.getItem('dms_owner_profile');
      return data ? JSON.parse(data) : null;
    } catch {
      return null;
    }
  },

  /**
   * Check if token or session is active.
   */
  isAuthenticated() {
    return Boolean(localStorage.getItem('dms_owner_token') || localStorage.getItem('dms_owner_profile'));
  },

  /**
   * Driver facial biometric registration.
   */
  async registerDriver(driverData) {
    const res = await apiClient.post('/auth/register', driverData);
    return res.data;
  },

  /**
   * Driver facial biometric authentication.
   */
  async authenticateDriver(frameB64) {
    const res = await apiClient.post('/auth/authenticate', { frame_b64: frameB64 });
    return res.data;
  },
};

