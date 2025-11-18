<template>
  <div>
    <div class="partners-banner">
      <img src="/lpde.png" alt="LPDE Logo" class="partner-logo" />
      
      <div class="separator"></div>

      <a href="https://www.silae.fr" target="_blank" class="logo-link">
        <img src="/prelium.gif" alt="Silae Logo" class="partner-logo" />
      </a>
      
      <div class="separator"></div>

      <a href="https://www.odoo.com" target="_blank" class="logo-link">
        <img src="/odoo.png" alt="Odoo Logo" class="partner-logo" />
      </a>
    </div>

    <h1>📊 Journal des Exécutions</h1>
    
    <div class="card">
      <button @click="loadLogs" class="btn-primary" style="margin-bottom: 15px;">Rafraîchir</button>
      <div v-if="loading">Chargement...</div>
      <table v-else>
        <thead>
          <tr>
            <th>Date</th>
            <th>Client</th>
            <th>Période</th>
            <th>Statut</th>
            <th>Message</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="log in logs" :key="log.client_doc_id + log.execution_time">
            <td>{{ formatDate(log.execution_time) }}</td>
            <td>{{ log.client_name }}</td>
            <td>{{ log.period }}</td>
            <td :class="getStatusClass(log.status)">{{ log.status }}</td>
            <td>{{ log.message }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import api from '../api';
import { DateTime } from 'luxon';

const logs = ref([]);
const loading = ref(false);

const loadLogs = async () => {
  loading.value = true;
  try {
    const res = await api.get('/api/logs');
    logs.value = res.data;
  } catch (e) {
    console.error(e);
  } finally {
    loading.value = false;
  }
};

const formatDate = (isoStr) => {
  if (!isoStr) return '-';
  return DateTime.fromISO(isoStr).toFormat('dd/MM/yyyy HH:mm');
};

const getStatusClass = (status) => {
  if (status && status.includes('SUCCESS')) return 'status-success';
  if (status && status.includes('ERROR')) return 'status-error';
  return '';
};

onMounted(loadLogs);
</script>

<style scoped>
.partners-banner {
  display: flex;
  justify-content: space-evenly; /* Distribue l'espace uniformément */
  align-items: center;
  background-color: white;
  padding: 25px 20px;
  border-radius: 12px;
  box-shadow: 0 4px 6px rgba(0,0,0,0.05);
  margin-bottom: 30px;
}

.partner-logo {
  height: 55px; /* Taille uniforme pour les 3 logos */
  width: auto;
  object-fit: contain; /* Assure que le logo n'est pas déformé */
  transition: transform 0.2s;
}

.partner-logo:hover {
  transform: scale(1.05);
}

.separator {
  height: 40px;
  width: 1px;
  background-color: #e2e8f0; /* Ligne grise verticale fine */
}

.btn-primary {
    background-color: #3b82f6;
    color: white;
    padding: 10px 20px;
    border: none;
    border-radius: 6px;
    cursor: pointer;
}
</style>