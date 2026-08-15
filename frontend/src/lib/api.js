import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API_BASE = `${BACKEND_URL}/api`;

export const api = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
});

api.interceptors.request.use((config) => {
  try {
    const token = localStorage.getItem('oh_token');
    if (token) {
      config.headers = config.headers || {};
      config.headers.Authorization = `Bearer ${token}`;
    }
  } catch {
    // ignore
  }
  return config;
});

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err?.response?.status === 401) {
      try {
        localStorage.removeItem('oh_token');
      } catch {
        // ignore
      }
      // We don't auto-redirect here to avoid loops; UI reacts via AuthProvider.
    }
    return Promise.reject(err);
  },
);

export const AuthAPI = {
  login: (email) => api.post('/auth/login', { email }).then((r) => r.data),
  me: () => api.get('/auth/me').then((r) => r.data),
};

export const ProjectAPI = {
  list: () => api.get('/projects').then((r) => r.data),
  create: (payload) => api.post('/projects', payload).then((r) => r.data),
  get: (id) => api.get(`/projects/${id}`).then((r) => r.data),
  remove: (id) => api.delete(`/projects/${id}`).then((r) => r.data),
  seedLabkot: () => api.post('/projects/seed/labkot').then((r) => r.data),
};

export const ContextAPI = {
  list: (pid) => api.get(`/projects/${pid}/contexts`).then((r) => r.data),
  add: (pid, payload) => api.post(`/projects/${pid}/contexts`, payload).then((r) => r.data),
  remove: (pid, sid) => api.delete(`/projects/${pid}/contexts/${sid}`).then((r) => r.data),
};

export const CacheAPI = {
  build: (pid) => api.post(`/projects/${pid}/cache/build`).then((r) => r.data),
  latest: (pid) => api.get(`/projects/${pid}/cache`).then((r) => r.data),
  history: (pid) => api.get(`/projects/${pid}/cache/history`).then((r) => r.data),
  incremental: (pid) => api.get(`/projects/${pid}/cache/incremental`).then((r) => r.data),
};

export const TaskAPI = {
  create: (pid, description) => api.post(`/projects/${pid}/tasks`, { description }).then((r) => r.data),
  list: (pid) => api.get(`/projects/${pid}/tasks`).then((r) => r.data),
};

export const AnalyticsAPI = {
  summary: () => api.get('/analytics').then((r) => r.data),
  history: () => api.get('/analytics/history').then((r) => r.data),
};

export const ConnectionAPI = {
  catalog: () => api.get('/connections/catalog').then((r) => r.data),
  list: () => api.get('/connections').then((r) => r.data),
  connect: (agent_key, agent_name) =>
    api.post('/connections', { agent_key, agent_name }).then((r) => r.data),
  disconnect: (id) => api.delete(`/connections/${id}`).then((r) => r.data),
};

export const UsageAPI = {
  planAdvisor: () => api.get('/usage/plan-advisor').then((r) => r.data),
};
