<template>
  <div>
    <h1>⚡ Import Manuel</h1>
    
    <div class="card">
      <h3>1. Sélectionner un client</h3>
      <select v-model="selectedClientDocId">
        <option value="" disabled>-- Choisir un client --</option>
        <option v-for="(client, id) in clients" :key="id" :value="id">
          {{ client.nom }}
        </option>
      </select>
    </div>

    <div class="card" v-if="selectedClientDocId">
      <h3>2. Sélectionner les périodes</h3>
      <div class="periods-grid">
        <label v-for="period in periodList" :key="period" class="period-checkbox">
          <input type="checkbox" :value="period" v-model="selectedPeriods" />
          {{ period }}
        </label>
      </div>
      
      <div style="margin-top: 20px; border-top: 1px solid #eee; padding-top: 20px;">
        <button @click="runImport" class="btn-primary" :disabled="loading || selectedPeriods.length === 0">
          <span v-if="loading">Traitement en cours...</span>
          <span v-else>Lancer l'import ({{ selectedPeriods.length }} périodes)</span>
        </button>
      </div>
    </div>

    <div v-if="results.length > 0" class="card" style="margin-top: 20px;">
        <h3>Résultats</h3>
        <ul>
            <li v-for="(res, index) in results" :key="index" :class="res.status === 'success' ? 'status-success' : 'status-error'">
                {{ res.period }} : {{ res.message }}
            </li>
        </ul>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue';
import api from '../api';
import { DateTime } from 'luxon';

const clients = ref({});
const selectedClientDocId = ref('');
const selectedPeriods = ref([]);
const loading = ref(false);
const results = ref([]);

// Générer les 24 derniers mois pour la liste
const periodList = computed(() => {
    const list = [];
    let date = DateTime.now();
    for (let i = 0; i < 24; i++) {
        list.push(date.toFormat('yyyy-MM'));
        date = date.minus({ months: 1 });
    }
    return list;
});

const loadClients = async () => {
    try {
        const res = await api.get('/api/clients');
        clients.value = res.data;
    } catch (e) {
        console.error("Erreur chargement clients", e);
    }
};

const runImport = async () => {
    if (!selectedClientDocId.value || selectedPeriods.value.length === 0) return;
    
    loading.value = true;
    results.value = []; // Reset results
    
    try {
        // On envoie la requête au backend
        // Note : Assurez-vous que la route /api/import/manual existe dans backend/main.py
        // Sinon cela renverra une erreur 404 ou 405 pour l'instant.
        const payload = {
            client_doc_id: selectedClientDocId.value,
            periods: selectedPeriods.value
        };
        
        const res = await api.post('/api/import/manual', payload);
        
        // On suppose que le backend renvoie un tableau de résultats
        if (res.data && res.data.results) {
            results.value = res.data.results;
        } else {
            results.value = [{ period: 'Global', status: 'success', message: 'Commande envoyée (voir logs)' }];
        }

    } catch (e) {
        results.value = [{ period: 'Erreur', status: 'error', message: e.response?.data?.detail || e.message }];
    } finally {
        loading.value = false;
    }
};

onMounted(loadClients);
</script>

<style scoped>
.periods-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
    gap: 10px;
    max-height: 200px;
    overflow-y: auto;
    border: 1px solid #eee;
    padding: 10px;
}
.period-checkbox {
    display: flex;
    align-items: center;
    gap: 5px;
    cursor: pointer;
    font-size: 0.9rem;
}
input[type="checkbox"] {
    width: auto; /* Override le style global */
    margin-bottom: 0;
}
</style>