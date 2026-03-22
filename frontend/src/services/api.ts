import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api',
});

// Note: localStorage is XSS-accessible. Acceptable for single-user dashboard;
// consider httpOnly cookies for production.
api.interceptors.request.use((config) => {
  const apiKey = localStorage.getItem('irt_api_key');
  if (apiKey) {
    config.headers['X-API-Key'] = apiKey;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('irt_api_key');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default api;
