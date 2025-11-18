<template>
  <div id="app-container">
    <aside class="sidebar">
      <div class="logo-container">
        <span class="app-title">PayFlow</span>
      </div>
      
      <nav>
        <router-link to="/" exact-active-class="active">📊 Journal</router-link>
        <router-link to="/manual-import" active-class="active">⚡ Import Manuel</router-link>
        <router-link to="/admin" active-class="active">⚙️ Admin Clients</router-link>
      </nav>
      
      <div class="sidebar-footer">
        <button @click="logout" class="logout-button">Déconnexion</button>
      </div>
    </aside>

    <main class="content">
      <router-view></router-view>
    </main>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router';

const router = useRouter();

const logout = () => {
  localStorage.removeItem('payflow-password');
  router.push('/login');
};
</script>

<style>
/* Styles généraux */
body {
  margin: 0;
  font-family: 'Inter', sans-serif;
  background-color: #f8fafc;
  color: #334155;
}

#app-container {
  display: flex;
  min-height: 100vh;
}

.sidebar {
  width: 250px;
  background-color: #2c3e50;
  color: white;
  padding: 20px;
  display: flex;
  flex-direction: column;
  box-shadow: 2px 0 5px rgba(0,0,0,0.1);
}

.logo-container {
  display: flex;
  align-items: center;
  justify-content: center; /* Ajouté pour centrer le titre */
  margin-bottom: 40px; /* Un peu plus d'espace sous le titre */
  padding-bottom: 20px;
  border-bottom: 1px solid #475569; /* Petite ligne de séparation esthétique */
}

/* .logo-main a été supprimé car l'image n'est plus là */

.app-title {
  font-size: 1.8rem;
  font-weight: bold;
  color: #f1f5f9;
  letter-spacing: 1px; /* Espacement léger pour le style */
}

nav {
  flex-grow: 1;
  display: flex;
  flex-direction: column;
}

nav a {
  color: #cbd5e1;
  text-decoration: none;
  padding: 12px 15px;
  margin: 5px 0;
  border-radius: 8px;
  transition: background-color 0.3s, color 0.3s;
  display: flex;
  align-items: center;
}

nav a:hover,
nav a.active {
  background-color: #475569;
  color: #e2e8f0;
}

.content {
  flex-grow: 1;
  padding: 30px;
  max-width: calc(100% - 250px);
}

.card {
  background-color: white;
  border-radius: 8px;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
  padding: 25px;
  margin-bottom: 20px;
}

/* Formulaires */
label {
  display: block;
  margin-bottom: 8px;
  font-weight: 600;
  color: #475569;
}

input[type="text"],
input[type="password"],
input[type="number"],
select {
  width: 100%;
  padding: 10px 12px;
  margin-bottom: 15px;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  font-size: 1rem;
  box-sizing: border-box;
}

input[type="text"]:focus,
input[type="password"]:focus,
input[type="number"]:focus,
select:focus {
  outline: none;
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.25);
}

button {
  background-color: #3b82f6;
  color: white;
  padding: 10px 20px;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-size: 1rem;
  transition: background-color 0.3s ease;
}

button:hover {
  background-color: #2563eb;
}

button:disabled {
  background-color: #93c5fd;
  cursor: not-allowed;
}

.logout-button {
  background-color: #ef4444;
  margin-top: auto;
  width: 100%;
}

.logout-button:hover {
  background-color: #dc2626;
}

/* Tableau */
table {
  width: 100%;
  border-collapse: collapse;
  margin-top: 20px;
  background-color: white;
  box-shadow: 0 2px 4px rgba(0,0,0,0.05);
  border-radius: 8px;
  overflow: hidden;
}

th, td {
  padding: 12px 15px;
  text-align: left;
  border-bottom: 1px solid #e2e8f0;
}

th {
  background-color: #f1f5f9;
  font-weight: 600;
  color: #475569;
}

tr:last-child td {
  border-bottom: none;
}

.status-success {
  color: #16a34a;
  font-weight: bold;
}
.status-error {
  color: #dc2626;
  font-weight: bold;
}

.sidebar-footer {
  margin-top: auto;
  padding-top: 20px;
  border-top: 1px solid #475569;
}
</style>