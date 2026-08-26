import axios from 'axios';

/**
 * Central API Client configuration for FastAPI integration
 */
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
    Accept: 'application/json',
  },
});

// Interceptor for uniform error logging
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    console.warn(`[API Error] ${error.config?.url || 'Request'} failed:`, error.message);
    return Promise.reject(error);
  }
);
