<template>
  <div class="admin-container">
    <div class="header-actions">
      <h1>⚙️ Administration des Clients</h1>
    </div>
    
    <!-- 1. Sélecteur de client (Card principale) -->
    <div class="card selector-card">
      <label class="section-label">Sélectionner un client à modifier</label>
      <div class="select-wrapper">
        <select v-model="selectedClientId" @change="loadClientDetails">
          <option value="">➕ Créer un Nouveau Client</option>
          <option v-for="(client, id) in clientsList" :key="id" :value="id">
            📂 {{ client.nom }} (ID: {{ id }})
          </option>
        </select>
      </div>
    </div>

    <!-- 2. Formulaire (Apparaît toujours) -->
    <form @submit.prevent="saveClient" class="main-form">
      
      <!-- SECTION 1 : SILAE -->
      <div class="form-section">
        <div class="section-header">
          <span class="icon">📄</span>
          <h3>1. Informations Silae</h3>
        </div>
        <div class="section-body">
          <div class="grid-3">
            <div class="input-group">
              <label>Numéro Dossier (ID Unique)</label>
              <input v-model="form.numero_dossier_silae" required :disabled="!!selectedClientId" placeholder="Ex: 12345" />
              <small>Identifiant unique du dossier dans Silae.</small>
            </div>
            <div class="input-group">
              <label>Nom du Client</label>
              <input v-model="form.nom" required placeholder="Ex: Ma Société SARL" />
            </div>
            <div class="input-group">
              <label>Jour du transfert</label>
              <input type="number" v-model="form.jour_transfert" required min="1" max="31" placeholder="1" />
              <small>Jour du mois où l'automate s'exécute.</small>
            </div>
          </div>
        </div>
      </div>

      <!-- SECTION 2 : ODOO -->
      <div class="form-section">
        <div class="section-header">
          <span class="icon">🟣</span>
          <h3>2. Connexion Odoo</h3>
        </div>
        <div class="section-body">
          <div class="grid-2">
            <div class="input-group">
              <label>Hôte Odoo</label>
              <div class="input-prefix">https://</div>
              <input v-model="form.odoo_host" required placeholder="ma-societe.odoo.com" class="with-prefix" />
            </div>
            <div class="input-group">
              <label>Base de données</label>
              <input v-model="form.database_odoo" required placeholder="Ex: ma-societe" />
            </div>
            <div class="input-group">
              <label>Login (Email)</label>
              <input v-model="form.odoo_login" required placeholder="admin@example.com" />
            </div>
            <div class="input-group">
              <label>Clé API / Mot de passe</label>
              <input type="password" v-model="form.odoo_password" placeholder="••••••••" />
              <small v-if="selectedClientId" style="color: #eab308;">Laisser vide pour conserver l'actuel.</small>
            </div>
          </div>

          <!-- Zone de Test -->
          <div class="test-area">
            <button type="button" @click="testConnection" class="btn-test" :disabled="testing">
              <span v-if="testing">🔌 Connexion en cours...</span>
              <span v-else>🔄 Tester la connexion & Charger les données</span>
            </button>
            
            <!-- Feedback Visuel -->
            <transition name="fade">
              <div v-if="testMessage" :class="['alert', testStatus === 'success' ? 'alert-success' : 'alert-error']">
                {{ testMessage }}
              </div>
            </transition>
          </div>
        </div>
      </div>

      <!-- SECTION 3 : COMPTABILITÉ -->
      <div class="form-section" :class="{ 'disabled-section': !hasOptions && !form.odoo_company_id }">
        <div class="section-header">
          <span class="icon">📊</span>
          <h3>3. Configuration Comptable</h3>
        </div>
        <div class="section-body">
          <p v-if="!hasOptions && !form.odoo_company_id" class="info-text">
            💡 Veuillez tester la connexion ci-dessus pour charger les sociétés et journaux disponibles.
          </p>
          
          <div class="grid-2">
            <div class="input-group">
              <label>Société Odoo (Multi-société)</label>
              <select v-model="form.odoo_company_id" required>
                <option :value="0" disabled>-- Sélectionner --</option>
                <option v-for="(name, id) in odooOptions.companies" :key="id" :value="id">
                  🏢 {{ name }} (ID: {{ id }})
                </option>
                <option v-if="!hasOptions && form.odoo_company_id" :value="form.odoo_company_id">
                  ID Actuel : {{ form.odoo_company_id }}
                </option>
              </select>
            </div>

            <div class="input-group">
              <label>Journal de Paie</label>
              <select v-model="form.journal_paie_odoo" required>
                <option value="" disabled>-- Sélectionner --</option>
                <!-- Modification ICI : Ajout du nom de la société -->
                <option v-for="j in odooOptions.journals" :key="j.code" :value="j.code">
                  📒 [{{ j.code }}] {{ j.name }} {{ formatJournalCompany(j) }}
                </option>
                
                <option v-if="!hasOptions && form.journal_paie_odoo" :value="form.journal_paie_odoo">
                  Code Actuel : {{ form.journal_paie_odoo }}
                </option>
              </select>
            </div>
          </div>
        </div>
      </div>

      <!-- Actions -->
      <div class="form-actions">
        <button type="submit" class="btn-primary big-btn">
          💾 Enregistrer le Client
        </button>
      </div>

    </form>
  </div>
</template>

<script setup>
import { ref, onMounted, reactive, computed } from 'vue';
import api from '../api';

const clientsList = ref({});
const selectedClientId = ref('');
const testing = ref(false);
const testMessage = ref('');
const testStatus = ref('');

const odooOptions = reactive({
  companies: {},
  journals: []
});

const form = reactive({
    numero_dossier_silae: '',
    nom: '',
    jour_transfert: 1,
    odoo_host: '',
    database_odoo: '',
    odoo_login: '',
    odoo_password: '',
    journal_paie_odoo: '',
    odoo_company_id: 0
});

const hasOptions = computed(() => Object.keys(odooOptions.companies).length > 0);

// Helper pour afficher la société du journal
const formatJournalCompany = (journal) => {
  if (journal.company_id && Array.isArray(journal.company_id) && journal.company_id.length > 1) {
    return `(🏢 ${journal.company_id[1]})`;
  }
  return '';
};

const loadClients = async () => {
    try {
        const res = await api.get('/api/clients');
        clientsList.value = res.data;
    } catch (e) {
        console.error("Erreur chargement clients", e);
    }
};

const loadClientDetails = () => {
    testMessage.value = '';
    odooOptions.companies = {};
    odooOptions.journals = [];

    if (!selectedClientId.value) {
        Object.keys(form).forEach(k => form[k] = '');
        form.jour_transfert = 1;
        form.odoo_company_id = 0;
        return;
    }
    
    const data = clientsList.value[selectedClientId.value];
    Object.assign(form, data);
    form.numero_dossier_silae = selectedClientId.value;
    form.odoo_password = ''; 
};

const testConnection = async () => {
    if (!form.odoo_host || !form.database_odoo || !form.odoo_login || !form.odoo_password) {
        testStatus.value = 'error';
        testMessage.value = "⚠️ Veuillez remplir tous les champs de connexion Odoo (y compris le mot de passe).";
        return;
    }

    testing.value = true;
    testMessage.value = '';
    
    try {
        const res = await api.post('/api/test-odoo', form);
        odooOptions.companies = res.data.companies;
        odooOptions.journals = res.data.journals;
        testStatus.value = 'success';
        testMessage.value = `✅ Connexion réussie ! ${Object.keys(res.data.companies).length} société(s) et ${res.data.journals.length} journaux trouvés.`;
        
        if (Object.keys(res.data.companies).length === 1 && !form.odoo_company_id) {
             form.odoo_company_id = parseInt(Object.keys(res.data.companies)[0]);
        }
    } catch (e) {
        testStatus.value = 'error';
        testMessage.value = "❌ " + (e.response?.data?.detail || "Erreur de connexion. Vérifiez les identifiants.");
    } finally {
        testing.value = false;
    }
};

const saveClient = async () => {
    if (!form.numero_dossier_silae) {
        alert("Le numéro de dossier Silae est requis.");
        return;
    }
    try {
        const docId = form.numero_dossier_silae;
        await api.post(`/api/clients/${docId}`, form);
        alert('Client sauvegardé avec succès !');
        loadClients();
    } catch (e) {
        alert('Erreur lors de la sauvegarde : ' + e.message);
    }
};

onMounted(loadClients);
</script>

<style scoped>
/* Structure Globale */
.admin-container {
  max-width: 1000px;
  margin: 0 auto;
}

h1 {
  color: #1e293b;
  margin-bottom: 20px;
}

/* Cards & Sections */
.card {
  background: white;
  padding: 20px;
  border-radius: 12px;
  box-shadow: 0 2px 10px rgba(0,0,0,0.05);
  margin-bottom: 20px;
}

.selector-card {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
}

.form-section {
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  margin-bottom: 25px;
  overflow: hidden;
  box-shadow: 0 2px 5px rgba(0,0,0,0.02);
}

.section-header {
  background: #f1f5f9;
  padding: 15px 20px;
  display: flex;
  align-items: center;
  gap: 10px;
  border-bottom: 1px solid #e2e8f0;
}

.section-header h3 {
  margin: 0;
  font-size: 1.1rem;
  color: #334155;
}

.section-header .icon {
  font-size: 1.2rem;
}

.section-body {
  padding: 25px;
}

/* Grilles */
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 25px; }
.grid-3 { display: grid; grid-template-columns: 1fr 2fr 1fr; gap: 25px; }

/* Inputs Modernes */
.input-group {
  display: flex;
  flex-direction: column;
  position: relative;
}

label {
  font-weight: 600;
  font-size: 0.9rem;
  color: #475569;
  margin-bottom: 8px;
}

input, select {
  padding: 12px;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  font-size: 0.95rem;
  transition: all 0.2s;
  background: #fff;
}

input:disabled {
  background: #f1f5f9;
  color: #94a3b8;
}

input:focus, select:focus {
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  outline: none;
}

/* Input avec préfixe (https://) */
.input-prefix {
  position: absolute;
  top: 38px; /* Ajuster selon le label */
  left: 1px;
  background: #f1f5f9;
  padding: 13px 10px;
  border-right: 1px solid #cbd5e1;
  border-radius: 8px 0 0 8px;
  color: #64748b;
  font-size: 0.9rem;
  pointer-events: none;
}
input.with-prefix {
  padding-left: 70px;
}

small {
  font-size: 0.8rem;
  color: #94a3b8;
  margin-top: 5px;
}

/* Boutons */
.btn-test {
  width: 100%;
  padding: 12px;
  background: #e2e8f0;
  color: #334155;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s;
}

.btn-test:hover {
  background: #cbd5e1;
}

.btn-primary {
  background: #3b82f6;
  color: white;
  padding: 15px 40px;
  font-size: 1.1rem;
  border: none;
  border-radius: 8px;
  font-weight: bold;
  cursor: pointer;
  box-shadow: 0 4px 6px rgba(59, 130, 246, 0.2);
  transition: transform 0.1s;
}

.btn-primary:hover {
  background: #2563eb;
  transform: translateY(-1px);
}

.form-actions {
  text-align: right;
  margin-top: 10px;
}

/* Alerts Feedback */
.test-area {
  margin-top: 20px;
}

.alert {
  margin-top: 15px;
  padding: 12px;
  border-radius: 8px;
  font-size: 0.95rem;
  text-align: center;
}

.alert-success {
  background: #dcfce7;
  color: #166534;
  border: 1px solid #bbf7d0;
}

.alert-error {
  background: #fee2e2;
  color: #991b1b;
  border: 1px solid #fecaca;
}

.info-text {
  color: #64748b;
  font-style: italic;
  text-align: center;
  margin-bottom: 15px;
}

.disabled-section {
  opacity: 0.7;
  pointer-events: none;
}

/* Animations */
.fade-enter-active, .fade-leave-active {
  transition: opacity 0.3s;
}
.fade-enter-from, .fade-leave-to {
  opacity: 0;
}
</style>