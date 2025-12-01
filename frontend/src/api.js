import axios from 'axios';
import router from './router';

const api = axios.create({
  baseURL: '', // Relatif
});

// Ajouter le mot de passe à chaque requête
api.interceptors.request.use(config => {
  // CORRECTION ICI : On s'assure d'utiliser la même clé que dans Login.vue
  const pwd = localStorage.getItem('payflow-password'); 
  
  if (pwd) {
    // On encode en Base64 pour éviter les problèmes d'accents/caractères spéciaux dans les headers
    // Note : Pour l'instant on l'envoie en clair comme le backend l'attend, 
    // mais le backend doit être capable de lire les caractères spéciaux.
    // Si votre mot de passe contient des accents, cela peut poser souci.
    // Restons simple pour le fix immédiat :
    config.headers['x-app-password'] = pwd;
  }
  return config;
});

// Gérer les erreurs 401 (Non autorisé)
api.interceptors.response.use(response => response, error => {
  if (error.response && error.response.status === 401) {
    // Si le backend refuse le mot de passe, on déconnecte l'utilisateur
    localStorage.removeItem('payflow-password');
    router.push('/login');
  }
  return Promise.reject(error);
});

export default api;