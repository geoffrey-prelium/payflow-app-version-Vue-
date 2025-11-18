import axios from 'axios';
import router from './router';

const api = axios.create({
  baseURL: '', // Relatif, car servira sur le même domaine en prod
});

// Ajouter le mot de passe à chaque requête
api.interceptors.request.use(config => {
  const pwd = localStorage.getItem('payflow_password');
  if (pwd) {
    config.headers['x-app-password'] = pwd;
  }
  return config;
});

// Gérer les erreurs 401 (Non autorisé)
api.interceptors.response.use(response => response, error => {
  if (error.response && error.response.status === 401) {
    localStorage.removeItem('payflow_password');
    router.push('/login');
  }
  return Promise.reject(error);
});

export default api;