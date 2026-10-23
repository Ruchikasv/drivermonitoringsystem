import axios from 'axios';

/**
 * Central API Client configuration for FastAPI integration with Owner Auth & Cookies
 */
export const getApiBaseUrl = () => {
  if (import.meta.env.VITE_API_BASE_URL) {
    return import.meta.env.VITE_API_BASE_URL;
  }
  if (typeof window !== 'undefined' && window.location) {
    const { protocol, hostname } = window.location;
    return `${protocol}//${hostname}:8000`;
  }
  return 'http://127.0.0.1:8000';
};

export const apiClient = axios.create({
  baseURL: getApiBaseUrl(),
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
    // Keep baseURL synchronized with current origin if not explicitly configured
    if (!config.baseURL || config.baseURL === 'http://127.0.0.1:8000') {
      config.baseURL = getApiBaseUrl();
    }
    const isDriverPortal = typeof window !== 'undefined' && window.location?.pathname?.startsWith('/driver');
    const token = !isDriverPortal ? localStorage.getItem('dms_owner_token') : null;
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
    const detailMsg = error.response?.data?.detail;
    const isNetworkErr = error.message === 'Network Error' || error.code === 'ERR_NETWORK';
    const msg = detailMsg || (isNetworkErr ? `Backend unreachable at ${getApiBaseUrl()}. Ensure server is running on port 8000.` : error.message);
    console.warn(`[API Error] ${error.config?.url || 'Request'} failed:`, msg);
    return Promise.reject(error);
  }
);

