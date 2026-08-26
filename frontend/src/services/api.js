import axios from 'axios';

/**
 * Central API Client configuration for FastAPI integration with Owner Auth & Cookies
 */
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  withCredentials: true, // Automatically transmits HttpOnly session cookies
  headers: {
    'Content-Type': 'application/json',
    Accept: 'application/json',
  },
});

// Request interceptor to attach Bearer token fallback if available in localStorage/session
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('dms_owner_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Interceptor for uniform error handling & 401 redirect
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // If we got 401 and we are not already on login/register/driver pages
      const path = window.location.pathname;
      if (!path.startsWith('/owner/login') && !path.startsWith('/owner/register') && !path.startsWith('/driver')) {
        localStorage.removeItem('dms_owner_token');
        localStorage.removeItem('dms_owner_profile');
      }
    }
    console.warn(`[API Error] ${error.config?.url || 'Request'} failed:`, error.response?.data?.detail || error.message);
    return Promise.reject(error);
  }
);

