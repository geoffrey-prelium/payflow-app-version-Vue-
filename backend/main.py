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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- CLIENTS GCP ---
try:
    project_id = os.environ.get("GCP_PROJECT") or os.environ.get("GCLOUD_PROJECT")
    # On précise le nom de la base Firestore si nécessaire
    db = firestore.Client(project=project_id, database="payflow-db")
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

# --- UTILITAIRES ---
def get_secret(secret_name):
    if not secret_client: raise Exception("Secret Client HS")
    project_id = os.environ.get("GCP_PROJECT")
    name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
    response = secret_client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8").strip()

def get_encryption_key():
    key_data = get_secret("PAYFLOW_ENCRYPTION_KEY")
    return key_data

def verify_password(x_app_password: str = Header(None)):
    try:
        correct_password = get_secret("PAYFLOW_PASSWORD")
    except Exception:
        raise HTTPException(status_code=500, detail="Erreur lecture secret")
        
    if x_app_password != correct_password:
        raise HTTPException(status_code=401, detail="Mot de passe invalide")
    return True

# --- LOGIQUE MÉTIER ---

def get_silae_config():
    return {k: get_secret(f"SILAE_{k.upper()}") for k in ["client_id", "client_secret", "subscription_key"]}

def get_silae_token_manual(config):
    auth_url = "https://payroll-api-auth.silae.fr/oauth2/v2.0/token"
    data = {"grant_type": "client_credentials", "client_id": config['client_id'], "client_secret": config['client_secret'], "scope": "https://silaecloudb2c.onmicrosoft.com/36658aca-9556-41b7-9e48-77e90b006f34/.default"}
    r = requests.post(auth_url, data=data)
    r.raise_for_status()
    return r.json()["access_token"]

def get_silae_ecritures_manual(token, config, dossier, start, end):
    url = "https://payroll-api.silae.fr/payroll/v1/EcrituresComptables/EcrituresComptables4"
    headers = {"Authorization": f"Bearer {token}", "Ocp-Apim-Subscription-Key": config['subscription_key'], "Content-Type": "application/json", "dossiers": str(dossier)}
    body = {"numeroDossier": str(dossier), "periodeDebut": start.strftime("%Y-%m-%d"), "periodeFin": end.strftime("%Y-%m-%d"), "avecToutesLesRepartitionsAnalytiques": False}
    r = requests.post(url, headers=headers, json=body)
    r.raise_for_status()
    return r.json()

def import_to_odoo_logic(client_conf, ecritures, period_str, entry_date):
    try:
        # 1. Connexion
        url_common = f"https://{client_conf['odoo_host']}/xmlrpc/2/common"
        url_object = f"https://{client_conf['odoo_host']}/xmlrpc/2/object"
        db = client_conf['database_odoo']
        user = client_conf['odoo_login']
        pwd = client_conf['odoo_password']
        company_id = client_conf['odoo_company_id']

        common = xmlrpc.client.ServerProxy(url_common)
        uid = common.authenticate(db, user, pwd, {})
        if not uid: return "ERROR_AUTH", "Auth Odoo échouée"
        
        models = xmlrpc.client.ServerProxy(url_object)
        
        # 2. Données Silae (CORRECTIF PROVISIONS & NONETYPE)
        if not ecritures.get('ruptures'): return "SUCCESS_EMPTY", "Aucune donnée"
        
        lignes = []
        for rupture in ecritures['ruptures']:
            # Utilisation de 'or []' pour éviter l'erreur NoneType is not iterable
            lignes.extend(rupture.get('ecritures') or [])

        if not lignes: return "SUCCESS_EMPTY", "Journal vide"
        
        # 3. Journal
        j_ids = models.execute_kw(db, uid, pwd, 'account.journal', 'search', [[('code', '=', client_conf['journal_paie_odoo'])]])
        if not j_ids: return "ERROR_JOURNAL", f"Journal introuvable"
        journal_id = j_ids[0]
        
        # 4. Lignes (CORRECTIF ODOO 18)
        move_lines = []
        for l in lignes:
            # On tente d'abord avec company_id (Odoo 17 et moins)
            acc_domain = [('code', '=', l['compte']), ('company_id', '=', company_id)]
            
            try:
                acc_ids = models.execute_kw(db, uid, pwd, 'account.account', 'search', [acc_domain])
            except xmlrpc.client.Fault as e:
                # Si erreur "KeyError: company_id", on est sur Odoo 18+
                if "company_id" in str(e):
                    # Recherche par code uniquement, avec contexte société
                    acc_domain = [('code', '=', l['compte'])]
                    ctx = {'allowed_company_ids': [company_id], 'check_company': True}
                    acc_ids = models.execute_kw(db, uid, pwd, 'account.account', 'search', [acc_domain], {'context': ctx})
                else:
                    raise e

            if not acc_ids: return "ERROR_ACCOUNT", f"Compte {l['compte']} introuvable"
            
            move_lines.append((0, 0, {
                'account_id': acc_ids[0],
                'name': l['libelle'],
                'debit': l['valeur'] if l['sens'] == 'D' else 0.0,
                'credit': l['valeur'] if l['sens'] == 'C' else 0.0
            }))
            
        # 5. Libellé Personnalisé (SALAIRES MOIS ANNEE)
        try:
            y, m = period_str.split('-')
            months = ["", "JANVIER", "FEVRIER", "MARS", "AVRIL", "MAI", "JUIN", "JUILLET", "AOUT", "SEPTEMBRE", "OCTOBRE", "NOVEMBRE", "DECEMBRE"]
            month_name = months[int(m)]
            label_ref = f"SALAIRES {month_name} {y}"
        except:
            label_ref = f"SALAIRES {period_str}"

        # 6. Pièce
        move_vals = {
            'journal_id': journal_id,
            'ref': label_ref,
            'date': entry_date.strftime("%Y-%m-%d"),
            'line_ids': move_lines,
            'company_id': company_id
        }
        move_id = models.execute_kw(db, uid, pwd, 'account.move', 'create', [move_vals])
        return "SUCCESS", f"Pièce créée ID {move_id} ({label_ref})"

    except Exception as e:
        return "ERROR_ODOO", str(e)

def log_db(doc_id, name, period, status, msg):
    if db:
        log_id = f"{doc_id}_{period}_{datetime.now().strftime('%Y%m%dT%H%M%S')}"
        db.collection("payflow_logs").document(log_id).set({
            "client_doc_id": doc_id, "client_name": name, "period": period,
            "execution_time": datetime.utcnow(), "status": status, "message": str(msg)[:1500]
        })

# --- ROUTES ---
@app.post("/api/auth/login")
def login(request: LoginRequest):
    try:
        if request.password == get_secret("PAYFLOW_PASSWORD"):
            return {"status": "ok"}
        raise HTTPException(status_code=401)
    except: raise HTTPException(status_code=500)

@app.get("/api/logs", dependencies=[Depends(verify_password)])
def get_logs():
    logs = []
    if db:
        for doc in db.collection("payflow_logs").order_by("execution_time", direction="DESCENDING").limit(100).stream():
            d = doc.to_dict()
            if 'execution_time' in d: d['execution_time'] = d['execution_time'].isoformat()
            logs.append(d)
    return logs

@app.get("/api/clients", dependencies=[Depends(verify_password)])
def get_clients():
    clients = {}
    if db:
        for doc in db.collection("payflow_clients").stream():
            d = doc.to_dict()
            d['odoo_password'] = "••••••••" if d.get('odoo_password') else None
            clients[doc.id] = d
    return clients

@app.post("/api/clients/{doc_id}", dependencies=[Depends(verify_password)])
def save_client(doc_id: str, client: ClientConfig):
    data = client.dict()
    if client.odoo_password and client.odoo_password != "••••••••":
        f = Fernet(get_encryption_key())
        data['odoo_password'] = f.encrypt(client.odoo_password.encode()).decode()
    else:
        del data['odoo_password']
    if db: db.collection("payflow_clients").document(doc_id).set(data, merge=True)
    return {"status": "success"}

@app.post("/api/test-odoo", dependencies=[Depends(verify_password)])
def test_odoo_connection(config: Dict[str, Any]):
    try:
        pwd = config.get('odoo_password')
        url_common = f"https://{config['odoo_host']}/xmlrpc/2/common"
        url_object = f"https://{config['odoo_host']}/xmlrpc/2/object"
        
        common = xmlrpc.client.ServerProxy(url_common)
        uid = common.authenticate(config['database_odoo'], config['odoo_login'], pwd, {})
        if not uid: raise HTTPException(status_code=400, detail="Auth échouée")
            
        models = xmlrpc.client.ServerProxy(url_object)
        user_data = models.execute_kw(config['database_odoo'], uid, pwd, 'res.users', 'read', [uid], {'fields': ['company_ids']})
        company_ids = user_data[0]['company_ids']
        companies = {c['id']: c['name'] for c in models.execute_kw(config['database_odoo'], uid, pwd, 'res.company', 'read', [company_ids], {'fields': ['name']})}
        
        # On récupère aussi company_id pour l'affichage
        journals = models.execute_kw(config['database_odoo'], uid, pwd, 'account.journal', 'search_read', [[('type', 'in', ['bank', 'cash', 'sale', 'purchase', 'general'])]], {'fields': ['name', 'code', 'company_id']})
        
        return {"status": "success", "companies": companies, "journals": journals}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/import/manual", dependencies=[Depends(verify_password)])
def run_manual_import(req: ManualImportRequest):
    results = []
    try:
        token = get_silae_token_manual(get_silae_config())
        client_ref = db.collection("payflow_clients").document(req.client_doc_id).get()
        if not client_ref.exists: raise HTTPException(status_code=404)
        client_data = client_ref.to_dict()
        
        f = Fernet(get_encryption_key())
        client_data['odoo_password'] = f.decrypt(client_data['odoo_password'].encode()).decode()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    for period in req.periods:
        try:
            d = datetime.strptime(period, "%Y-%m")
            next_m = d.replace(year=d.year+1, month=1) if d.month == 12 else d.replace(month=d.month+1)
            end = next_m - pd.Timedelta(days=1)
            
            ecritures = get_silae_ecritures_manual(token, get_silae_config(), client_data['numero_dossier_silae'], d, end)
            status, msg = import_to_odoo_logic(client_data, ecritures, period, end)
            
            log_db(req.client_doc_id, client_data.get('nom'), period, f"MANUAL_{status}", msg)
            results.append({"period": period, "status": "success" if "SUCCESS" in status else "error", "message": msg})
        except Exception as e:
            log_db(req.client_doc_id, client_data.get('nom'), period, "MANUAL_CRASH", str(e))
            results.append({"period": period, "status": "error", "message": str(e)})
    return {"results": results}

# --- ASSETS ---
app.mount("/assets", StaticFiles(directory="/app/static/assets"), name="assets")
@app.get("/{full_path:path}")
async def serve_vue_app(full_path: str):
    if full_path.startswith("api"): raise HTTPException(status_code=404)
    file_path = f"/app/static/{full_path}"
    if os.path.exists(file_path) and os.path.isfile(file_path): return FileResponse(file_path)
    return FileResponse("/app/static/index.html")