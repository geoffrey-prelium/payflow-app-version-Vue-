import os
import json
import traceback
from datetime import datetime
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException, Header, Depends, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from google.cloud import firestore, secretmanager
from cryptography.fernet import Fernet
import xmlrpc.client
import requests
import pandas as pd

# --- CONFIGURATION ---
app = FastAPI(title="PayFlow API")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- CLIENTS GCP ---
try:
    # Note: Assurez-vous que la base 'payflow-db' existe bien, sinon enlevez database="..."
    db = firestore.Client(database="payflow-db")
    secret_client = secretmanager.SecretManagerServiceClient()
except Exception as e:
    print(f"Erreur init GCP: {e}")
    db = None
    secret_client = None

# --- MODÈLES PYDANTIC ---
class LoginRequest(BaseModel):
    password: str

class ClientConfig(BaseModel):
    nom: str
    numero_dossier_silae: str
    jour_transfert: int
    odoo_host: str
    database_odoo: str
    odoo_login: str
    odoo_password: Optional[str] = None
    journal_paie_odoo: str
    odoo_company_id: int

class ManualImportRequest(BaseModel):
    client_doc_id: str
    periods: List[str]

# --- UTILITAIRES GCP ---
def get_project_id():
    return os.environ.get("GCP_PROJECT") or os.environ.get("GCLOUD_PROJECT")

def get_secret(secret_name):
    if not secret_client: raise Exception("Secret Client non initialisé")
    project_id = get_project_id()
    name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
    response = secret_client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8").strip()

def get_encryption_key():
    if not secret_client: raise Exception("Secret Client non initialisé")
    project_id = get_project_id()
    name = f"projects/{project_id}/secrets/PAYFLOW_ENCRYPTION_KEY/versions/latest"
    response = secret_client.access_secret_version(request={"name": name})
    return response.payload.data

# --- SÉCURITÉ ---
def verify_password(x_app_password: str = Header(None)):
    try:
        correct_password = get_secret("PAYFLOW_PASSWORD")
        if x_app_password != correct_password:
            raise HTTPException(status_code=401, detail="Mot de passe invalide")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur auth: {str(e)}")
    return True

# --- LOGIQUE MÉTIER (SILAE / ODOO / LOGS) ---

def get_silae_config():
    config = {}
    keys = ["SILAE_CLIENT_ID", "SILAE_CLIENT_SECRET", "SILAE_SUBSCRIPTION_KEY"]
    for k in keys:
        val = get_secret(k)
        config[k.lower().replace("silae_", "")] = val
    return config

def get_silae_token_manual(config):
    auth_url = "https://payroll-api-auth.silae.fr/oauth2/v2.0/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": config['client_id'],
        "client_secret": config['client_secret'],
        "scope": "https://silaecloudb2c.onmicrosoft.com/36658aca-9556-41b7-9e48-77e90b006f34/.default"
    }
    r = requests.post(auth_url, data=data)
    r.raise_for_status()
    return r.json()["access_token"]

def get_silae_ecritures_manual(token, config, dossier, start_date, end_date):
    url = "https://payroll-api.silae.fr/payroll/v1/EcrituresComptables/EcrituresComptables4"
    headers = {
        "Authorization": f"Bearer {token}",
        "Ocp-Apim-Subscription-Key": config['subscription_key'],
        "Content-Type": "application/json",
        "dossiers": str(dossier)
    }
    body = {
        "numeroDossier": str(dossier),
        "periodeDebut": start_date.strftime("%Y-%m-%d"),
        "periodeFin": end_date.strftime("%Y-%m-%d"),
        "avecToutesLesRepartitionsAnalytiques": False
    }
    r = requests.post(url, headers=headers, json=body)
    r.raise_for_status()
    return r.json()

def import_to_odoo_logic(client_conf, ecritures, period_str, entry_date):
    try:
        # 1. Connexion Odoo
        url_common = f"https://{client_conf['odoo_host']}/xmlrpc/2/common"
        url_object = f"https://{client_conf['odoo_host']}/xmlrpc/2/object"
        db_name = client_conf['database_odoo']
        user = client_conf['odoo_login']
        pwd = client_conf['odoo_password'] # Déjà décrypté
        company_id = client_conf['odoo_company_id']

        common = xmlrpc.client.ServerProxy(url_common)
        uid = common.authenticate(db_name, user, pwd, {})
        if not uid: return "ERROR_AUTH", "Auth Odoo échouée"
        
        models = xmlrpc.client.ServerProxy(url_object)
        
        # 2. Vérification Données Silae
        if not ecritures.get('ruptures'): return "SUCCESS_EMPTY", "Aucune donnée Silae"
        journal_silae = ecritures['ruptures'][0]
        lignes = journal_silae.get('ecritures', [])
        if not lignes: return "SUCCESS_EMPTY", "Journal vide"
        
        # 3. Récupération ID Journal Odoo
        j_ids = models.execute_kw(db_name, uid, pwd, 'account.journal', 'search', [[('code', '=', client_conf['journal_paie_odoo'])]])
        if not j_ids: return "ERROR_JOURNAL", f"Journal {client_conf['journal_paie_odoo']} introuvable"
        journal_id = j_ids[0]
        
        # 4. Préparation des lignes
        move_lines = []
        for l in lignes:
            # Recherche Compte (filtré par société)
            acc_domain = [('code', '=', l['compte']), ('company_id', '=', company_id)]
            acc_ids = models.execute_kw(db_name, uid, pwd, 'account.account', 'search', [acc_domain])
            
            # Si compte introuvable, on stop (ou on pourrait logger un warning)
            if not acc_ids: return "ERROR_ACCOUNT", f"Compte {l['compte']} introuvable"
            
            debit = l['valeur'] if l['sens'] == 'D' else 0.0
            credit = l['valeur'] if l['sens'] == 'C' else 0.0
            
            move_lines.append((0, 0, {
                'account_id': acc_ids[0],
                'name': l['libelle'],
                'debit': debit,
                'credit': credit
            }))
            
        # 5. Création de la pièce comptable
        move_vals = {
            'journal_id': journal_id,
            'ref': f"Paie {period_str}",
            'date': entry_date.strftime("%Y-%m-%d"),
            'line_ids': move_lines,
            'company_id': company_id
        }
        
        move_id = models.execute_kw(db_name, uid, pwd, 'account.move', 'create', [move_vals])
        return "SUCCESS", f"Pièce créée ID {move_id}"

    except Exception as e:
        return "ERROR_ODOO", str(e)

def log_db(doc_id, name, period, status, msg):
    try:
        if not db: return
        log_id = f"{doc_id}_{period}_{datetime.now().strftime('%Y%m%dT%H%M%S')}"
        db.collection("payflow_logs").document(log_id).set({
            "client_doc_id": doc_id, 
            "client_name": name, 
            "period": period,
            "execution_time": datetime.utcnow(), 
            "status": status, 
            "message": str(msg)[:1500]
        })
    except Exception as e:
        print(f"Erreur Log Firestore: {e}")

# --- ROUTES API ---

@app.post("/api/auth/login")
def login(request: LoginRequest):
    try:
        correct_password = get_secret("PAYFLOW_PASSWORD")
        if request.password == correct_password:
            return {"status": "ok"}
        else:
            raise HTTPException(status_code=401, detail="Mot de passe incorrect")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/logs", dependencies=[Depends(verify_password)])
def get_logs():
    logs = []
    if db:
        ref = db.collection("payflow_logs").order_by("execution_time", direction="DESCENDING").limit(100)
        for doc in ref.stream():
            data = doc.to_dict()
            if 'execution_time' in data:
                data['execution_time'] = data['execution_time'].isoformat()
            logs.append(data)
    return logs

@app.get("/api/clients", dependencies=[Depends(verify_password)])
def get_clients():
    clients = {}
    if db:
        ref = db.collection("payflow_clients").stream()
        for doc in ref:
            data = doc.to_dict()
            data['odoo_password'] = "••••••••" if data.get('odoo_password') else None
            clients[doc.id] = data
    return clients

@app.post("/api/clients/{doc_id}", dependencies=[Depends(verify_password)])
def save_client(doc_id: str, client: ClientConfig):
    try:
        data = client.dict()
        
        if client.odoo_password and client.odoo_password != "••••••••":
            key = get_encryption_key()
            f = Fernet(key)
            encrypted = f.encrypt(client.odoo_password.encode()).decode()
            data['odoo_password'] = encrypted
        else:
            del data['odoo_password']

        if db:
            db.collection("payflow_clients").document(doc_id).set(data, merge=True)
        return {"status": "success", "message": f"Client {client.nom} sauvegardé."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/test-odoo", dependencies=[Depends(verify_password)])
def test_odoo_connection(config: Dict[str, Any]):
    try:
        pwd = config.get('odoo_password')
        # Note: En prod, il faudrait gérer le cas où le password est vide (récup de BDD)
        # Ici on assume qu'on teste une nouvelle saisie
        
        url_common = f"https://{config['odoo_host']}/xmlrpc/2/common"
        url_object = f"https://{config['odoo_host']}/xmlrpc/2/object"
        
        common = xmlrpc.client.ServerProxy(url_common)
        uid = common.authenticate(config['database_odoo'], config['odoo_login'], pwd, {})
        
        if not uid: raise HTTPException(status_code=400, detail="Authentification Odoo échouée")
            
        models = xmlrpc.client.ServerProxy(url_object)
        
        # Compagnies
        user_data = models.execute_kw(config['database_odoo'], uid, pwd, 'res.users', 'read', [uid], {'fields': ['company_ids']})
        company_ids = user_data[0]['company_ids']
        companies_raw = models.execute_kw(config['database_odoo'], uid, pwd, 'res.company', 'read', [company_ids], {'fields': ['name']})
        companies = {c['id']: c['name'] for c in companies_raw}

        # Journaux
        journals = models.execute_kw(config['database_odoo'], uid, pwd, 'account.journal', 'search_read', [[('type', 'in', ['bank', 'cash', 'sale', 'purchase', 'general'])]], {'fields': ['name', 'code', 'company_id']})
        
        return {"status": "success", "companies": companies, "journals": journals}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erreur Odoo: {str(e)}")

@app.post("/api/import/manual", dependencies=[Depends(verify_password)])
def run_manual_import(req: ManualImportRequest):
    results = []
    try:
        silae_conf = get_silae_config()
        token = get_silae_token_manual(silae_conf)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur Silae Init: {str(e)}")

    # Récupérer infos client
    if not db: raise HTTPException(status_code=500, detail="DB non dispo")
    client_ref = db.collection("payflow_clients").document(req.client_doc_id).get()
    if not client_ref.exists:
        raise HTTPException(status_code=404, detail="Client introuvable")
    
    client_data = client_ref.to_dict()
    
    # Décryptage
    try:
        key = get_encryption_key()
        f = Fernet(key)
        decrypted_pwd = f.decrypt(client_data['odoo_password'].encode()).decode()
        client_data['odoo_password'] = decrypted_pwd
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur décryptage: {str(e)}")

    # Traitement
    for period in req.periods:
        try:
            d = datetime.strptime(period, "%Y-%m")
            start = d
            if d.month == 12:
                next_month = d.replace(year=d.year+1, month=1)
            else:
                next_month = d.replace(month=d.month+1)
            end = next_month - pd.Timedelta(days=1)

            ecritures = get_silae_ecritures_manual(token, silae_conf, client_data['numero_dossier_silae'], start, end)
            status, msg = import_to_odoo_logic(client_data, ecritures, period, end)
            
            log_db(req.client_doc_id, client_data.get('nom'), period, f"MANUAL_{status}", msg)
            results.append({"period": period, "status": "success" if "SUCCESS" in status else "error", "message": msg})
        except Exception as e:
            err_msg = str(e)
            log_db(req.client_doc_id, client_data.get('nom'), period, "MANUAL_CRASH", err_msg)
            results.append({"period": period, "status": "error", "message": err_msg})

    return {"results": results}

# 1. Monter les assets (JS/CSS générés par Vite)
app.mount("/assets", StaticFiles(directory="/app/static/assets"), name="assets")

# 2. Route intelligente pour servir VueJS OU les fichiers du dossier public
@app.get("/{full_path:path}")
async def serve_vue_app(full_path: str):
    # Si c'est une API, on laisse passer (ou 404 si pas trouvée avant)
    if full_path.startswith("api"):
        raise HTTPException(status_code=404)
    
    # Vérifier si le fichier demandé existe dans le dossier static (ex: /lpde.png)
    # Note: Dans le Docker, /app/frontend/dist est copié vers /app/static
    file_path = f"/app/static/{full_path}"
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return FileResponse(file_path)
    
    # Sinon, on renvoie l'index.html (pour que Vue Router gère la page)
    return FileResponse("/app/static/index.html")