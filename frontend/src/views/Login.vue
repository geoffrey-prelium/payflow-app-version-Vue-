<template>
  <div class="login-container">
    <div class="card login-card">
      <h2 style="text-align: center; margin-bottom: 20px;">🔒 Connexion PayFlow</h2>
      
      <form @submit.prevent="handleLogin">
        <div style="margin-bottom: 20px;">
          <input 
            type="password" 
            v-model="password" 
            placeholder="Mot de passe de l'application" 
            required 
            class="login-input"
          />
        </div>
        
        <button type="submit" class="btn-primary" style="width: 100%;" :disabled="loading">
          <span v-if="loading">Vérification...</span>
          <span v-else>Se connecter</span>
        </button>
      </form>
      
      <p v-if="error" class="error-msg">{{ error }}</p>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import axios from 'axios';

const password = ref('');
const error = ref('');
const loading = ref(false);
const router = useRouter();

const handleLogin = async () => {
  loading.value = true;
  error.value = '';
  
  try {
    // Appel API pour vérifier le mot de passe
    // Note: L'URL est relative, le proxy Vite ou le serveur Python gérera le /api
    await axios.post('/api/auth/login', { password: password.value });
    
    // SUCCÈS : On stocke le mot de passe avec la BONNE CLÉ (avec un tiret)
    localStorage.setItem('payflow-password', password.value);
    
    // On redirige vers l'accueil
    router.push('/');
    
  } catch (e) {
    console.error(e);
    if (e.response && e.response.status === 401) {
      error.value = "Mot de passe incorrect.";
    } else {
      error.value = "Erreur de connexion serveur.";
    }
  } finally {
    loading.value = false;
  }
};
</script>

<style scoped>
.login-container {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 80vh; /* Centre verticalement */
}

.login-card {
  width: 100%;
  max-width: 400px;
  padding: 40px;
}

.login-input {
  width: 100%;
  padding: 12px;
  font-size: 1.1rem;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  text-align: center; /* Esthétique pour un champ mdp unique */
}

.error-msg {
  color: #dc2626;
  text-align: center;
  margin-top: 15px;
  font-weight: bold;
}

.btn-primary {
    background-color: #3b82f6;
    color: white;
    padding: 12px 20px;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    font-size: 1rem;
}
</style>