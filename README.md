# 🌊 PayFlow - Connecteur de Paie Silae ↔

# Odoo

**PayFlow** est une solution d'automatisation cloud-native qui orchestre la récupération des
écritures comptables de paie depuis l'API **Silae** et leur injection automatique dans **Odoo** via
XML-RPC.
L'application offre une interface web moderne pour l'administration des dossiers clients et un
journal détaillé des exécutions.

## 🏗 Architecture Technique

Le projet adopte une architecture découplée (Decoupled Architecture) pour garantir
scalabilité et maintenance aisée.
**Composant Technologie Description Hébergement
Frontend Vue.js 3** (Vite) Interface utilisateur
réactive (SPA).
Cloud Run
**Backend FastAPI** (Python) API REST, gestion
de la sécurité et
proxy Odoo.
Cloud Run
**Automation Python 3.10** Robot autonome
d'import (Batch).
Cloud Functions
**Base de Données Firestore** NoSQL :
Configuration
clients & Logs.
Firestore
**Sécurité Secret Manager** Stockage des clés
API et mots de
passe.

#### GCP

### Flux de Données

1. **Scheduler** (Cron) déclenche le **Topic Pub/Sub** tous les jours à 06h00.
2. **Cloud Function** (Robot) se réveille, lit les clients à traiter ce jour-là dans **Firestore**.
3. Le Robot récupère les secrets via **Secret Manager**.
4. Il interroge **Silae** (API OAuth2) puis écrit dans **Odoo** (XML-RPC).


5. En cas d'erreur, une alerte **SMTP** (Infomaniak) est envoyée au client.

## 📂 Structure du Projet

payflow-vue/
├── backend/ # 🧠 API Serveur (FastAPI)
│ ├── main.py # Points d'entrée API & Logique métier
│ └── requirements.txt # Dépendances Python (FastAPI, Uvicorn...)
│
├── frontend/ # 🎨 Interface Utilisateur (Vue.js)
│ ├── src/ # Code source (Vues, Composants)
│ ├── public/ # Assets statiques (Logos)
│ └── ... # Config Vite & Package.json
│
├── automation/ # 🤖 Robot (Cloud Function)
│ ├── main.py # Script d'import auto & Mailing
│ └── requirements.txt # Dépendances légères pour le robot
│
├── Dockerfile # 🐳 Image conteneur pour Cloud Run (Front + Back)
└── README.md # Documentation

## 🔑 Configuration (Google Secret Manager)

L'application ne stocke aucun mot de passe en dur. Tous les secrets doivent être configurés
dans **GCP Secret Manager**.
**Nom du Secret Valeur Attendue**
PAYFLOW_PASSWORD Mot de passe maître pour accéder à
l'interface Web.
PAYFLOW_ENCRYPTION_KEY Clé Fernet (base64) pour chiffrer les mots
de passe Odoo en BDD.
SILAE_CLIENT_ID ID Client fourni par Silae (API).
SILAE_CLIENT_SECRET Clé secrète fournie par Silae.
SILAE_SUBSCRIPTION_KEY Clé d'abonnement API Silae
(Ocp-Apim-Subscription-Key).
PAYFLOW_EMAIL_SENDER Adresse email expéditrice (ex:


```
notifications@domaine.com).
PAYFLOW_EMAIL_PASSWORD Mot de passe de l'email (ou App Password
si 2FA actif).
```
## 🚀 Guide de Déploiement

Toutes les commandes doivent être exécutées depuis un terminal **PowerShell** à la racine du
projet.

### Pré-requis

$PROJECT_ID = "payflow-vue"
$REGION = "europe-west9"

### 1. Déployer l'Interface Web (Frontend + Backend)

Cette commande met à jour l'application accessible par les utilisateurs.
# 1. Construction de l'image Docker unifiée
gcloud builds submit --tag "gcr.io/$PROJECT_ID/payflow-app" --project $PROJECT_ID.
# 2. Déploiement sur Cloud Run
gcloud run deploy payflow-app `
--image "gcr.io/$PROJECT_ID/payflow-app" `
--platform managed `
--region $REGION `
--allow-unauthenticated `
--memory 512Mi `
--project $PROJECT_ID `
--set-env-vars "GCP_PROJECT=$PROJECT_ID"

### 2. Déployer le Robot (Automation)

Cette commande met à jour le script qui tourne en arrière-plan.
cd automation
gcloud functions deploy payflow-robot `
--gen2 `
--region $REGION `
--runtime python310 `
--entry-point process_monthly_import `


--trigger-topic payflow-daily-trigger `
--memory 512Mi `
--timeout 540s `
--project $PROJECT_ID `
--set-env-vars "GCP_PROJECT=$PROJECT_ID"
cd ..

### 3. Tester le Robot manuellement

Pour forcer une exécution immédiate sans attendre l'horaire programmé.
(Note : Le scheduler est en europe-west1 en raison des contraintes App Engine).
gcloud scheduler jobs run payflow-daily-job --location europe-west1 --project $PROJECT_ID

## 🛠 Développement Local

Pour travailler sur le projet sans déployer à chaque modification.

### Frontend (Vue.js)

Le serveur de développement supporte le Hot-Reload.
cd frontend
npm install
npm run dev

### Backend (FastAPI)

cd backend
pip install -r requirements.txt
# Note: Nécessite d'être authentifié via 'gcloud auth application-default login'
uvicorn main:app --reload

## 📧 Système d'Alertes

Le robot utilise le serveur SMTP Infomaniak (mail.infomaniak.com:587).
En cas d'échec lors d'un import automatique :

1. L'erreur est logguée dans Firestore.
2. Un email détaillé est envoyé à l'adresse définie dans le champ **"Login Odoo"** de la fiche
    client concernée.
Auteur : LPDE Cloud


Version : 2.0 (Architecture Vue/FastAPI)


