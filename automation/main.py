import base64
import json
import os
import traceback
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import xmlrpc.client
from urllib.parse import quote
import pandas as pd 
import requests
from google.cloud import firestore, secretmanager

try:
    from cryptography.fernet import Fernet
except ImportError:
    print("ERREUR CRITIQUE: 'cryptography' manquant.")
    Fernet = None

# --- CONFIGURATION SMTP (Infomaniak) ---
SMTP_HOST = "mail.infomaniak.com"
SMTP_PORT = 587

# --- Initialisation GCP ---
try:
    project_id = os.environ.get("GCP_PROJECT") or os.environ.get("GCLOUD_PROJECT")
    SECRET_CLIENT = secretmanager.SecretManagerServiceClient()
    DB = firestore.Client(project=project_id, database="payflow-db") 
except Exception as e:
    print(f"ERREUR CRITIQUE INIT: {e}")
    SECRET_CLIENT = None
    DB = None

# --- Fonctions Utilitaires ---

def get_secret(name):
    try:
        project_id = os.environ.get("GCP_PROJECT")
        path = f"projects/{project_id}/secrets/{name}/versions/latest"
        response = SECRET_CLIENT.access_secret_version(request={"name": path})
        return response.payload.data.decode("UTF-8").strip()
    except Exception as e:
        print(f"Erreur lecture secret {name}: {e}")
        return None

def get_encryption_key():
    key_data = get_secret("PAYFLOW_ENCRYPTION_KEY")
    if not key_data: raise Exception("Clé de cryptage introuvable")
    return key_data

def decrypt_data(encrypted_data, key):
    if not encrypted_data: return None
    try:
        f = Fernet(key)
        return f.decrypt(encrypted_data.encode()).decode()
    except Exception:
        return encrypted_data

def send_error_email(recipient_email, client_name, period, error_message):
    sender_email = get_secret("PAYFLOW_EMAIL_SENDER")
    sender_password = get_secret("PAYFLOW_EMAIL_PASSWORD")

    if not sender_email or not sender_password:
        print("⚠️ Secrets email manquants.")
        return

    if not recipient_email or "@" not in recipient_email:
        print(f"⚠️ Email destinataire invalide: {recipient_email}")
        return

    try:
        subject = f"❌ Échec Import PayFlow : {client_name} ({period})"
        body = f"""
        Bonjour,

        Le transfert automatique des écritures de paie a échoué pour le client : {client_name}.
        Période : {period}
        
        Erreur :
        {error_message}

        Cordialement,
        L'équipe PayFlow
        """
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = recipient_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, recipient_email, msg.as_string())
        server.quit()
        print(f"📧 Alerte envoyée à {recipient_email}")
    except Exception as e:
        print(f"❌ Erreur envoi mail : {e}")

# --- FONCTIONS MÉTIER ---

def get_silae_token(config):
    auth_url = "https://payroll-api-auth.silae.fr/oauth2/v2.0/token"
    data = {"grant_type": "client_credentials", "client_id": config['client_id'], "client_secret": config['client_secret'], "scope": "https://silaecloudb2c.onmicrosoft.com/36658aca-9556-41b7-9e48-77e90b006f34/.default"}
    r = requests.post(auth_url, data=data)
    r.raise_for_status()
    return r.json()["access_token"]

def get_silae_ecritures(token, config, dossier, start, end):
    url = "https://payroll-api.silae.fr/payroll/v1/EcrituresComptables/EcrituresComptables4"
    headers = {"Authorization": f"Bearer {token}", "Ocp-Apim-Subscription-Key": config['subscription_key'], "Content-Type": "application/json", "dossiers": str(dossier)}
    body = {"numeroDossier": str(dossier), "periodeDebut": start.strftime('%Y-%m-%d'), "periodeFin": end.strftime('%Y-%m-%d'), "avecToutesLesRepartitionsAnalytiques": False}
    r = requests.post(url, headers=headers, json=body)
    r.raise_for_status()
    return r.json()

def import_to_odoo_auto(client_config, ecritures_data, period_str, entry_date):
    host = client_config.get('odoo_host')
    db_name = client_config.get('database_odoo')
    username = client_config.get('odoo_login')
    password = client_config.get('odoo_password')
    journal_code = client_config.get('journal_paie_odoo')
    company_id = client_config.get('odoo_company_id')

    if not all([host, db_name, username, password, journal_code, company_id]):
        return "ERROR_CONFIG", "Configuration Odoo incomplète."

    try:
        if not ecritures_data.get('ruptures'): return "SUCCESS_EMPTY", "Aucune donnée Silae."
        
        # CORRECTIF PROVISIONS : On fusionne toutes les ruptures
        # AJOUT CORRECTIF "NoneType" : On utilise 'or []' pour éviter de planter si une rupture est vide/null
        lignes = []
        for rupture in ecritures_data['ruptures']:
            lignes.extend(rupture.get('ecritures') or [])

        if not lignes: return "SUCCESS_EMPTY", "Journal Silae vide."

        url_common = f"https://{host}/xmlrpc/2/common"
        url_object = f"https://{host}/xmlrpc/2/object"

        common = xmlrpc.client.ServerProxy(url_common)
        uid = common.authenticate(db_name, username, password, {})
        if not uid: return "ERROR_AUTH", "Échec authentification Odoo."

        models = xmlrpc.client.ServerProxy(url_object)
        
        j_ids = models.execute_kw(db_name, uid, password, 'account.journal', 'search', [[('code', '=', journal_code)]])
        if not j_ids: return "ERROR_JOURNAL", f"Journal {journal_code} introuvable."
        journal_id = j_ids[0]

        move_lines = []
        for l in lignes:
            # CORRECTIF ODOO 18
            acc_domain = [('code', '=', l['compte']), ('company_id', '=', company_id)]
            try:
                acc_ids = models.execute_kw(db_name, uid, password, 'account.account', 'search', [acc_domain])
            except xmlrpc.client.Fault as e:
                if "company_id" in str(e):
                    acc_domain = [('code', '=', l['compte'])]
                    ctx = {'allowed_company_ids': [company_id], 'check_company': True}
                    acc_ids = models.execute_kw(db_name, uid, password, 'account.account', 'search', [acc_domain], {'context': ctx})
                else:
                    raise e

            if not acc_ids: return "ERROR_ACCOUNT", f"Compte {l['compte']} introuvable."
            
            move_lines.append((0, 0, {
                'account_id': acc_ids[0],
                'name': l['libelle'],
                'debit': l['valeur'] if l['sens'] == 'D' else 0.0,
                'credit': l['valeur'] if l['sens'] == 'C' else 0.0
            }))

        # LIBELLÉ PERSONNALISÉ
        try:
            y, m = period_str.split('-')
            months = ["", "JANVIER", "FEVRIER", "MARS", "AVRIL", "MAI", "JUIN", "JUILLET", "AOUT", "SEPTEMBRE", "OCTOBRE", "NOVEMBRE", "DECEMBRE"]
            month_name = months[int(m)]
            label_ref = f"SALAIRES {month_name} {y}"
        except:
            label_ref = f"SALAIRES {period_str}"

        move_vals = {
            'journal_id': journal_id,
            'ref': label_ref,
            'date': entry_date.strftime('%Y-%m-%d'),
            'line_ids': move_lines,
            'company_id': company_id
        }
        
        move_id = models.execute_kw(db_name, uid, password, 'account.move', 'create', [move_vals])
        return "SUCCESS", f"Pièce créée ID {move_id} ({label_ref})"

    except Exception as e:
        return "ERROR_ODOO_RPC", str(e)

def log_execution(client_doc_id, client_name, period_str, status, message):
    if not DB: return
    try:
        log_id = f"{client_doc_id}_{period_str}_{datetime.now().strftime('%Y%m%dT%H%M%S')}"
        DB.collection("payflow_logs").document(log_id).set({
            "client_doc_id": client_doc_id, "client_name": client_name,
            "period": period_str, "execution_time": datetime.utcnow(),
            "status": status, "message": message[:1500]
        })
    except Exception as e:
        print(f"Erreur Log: {e}")

def process_monthly_import(event, context):
    print(f"--- Démarrage PayFlow Robot ---")
    today = datetime.utcnow()
    current_day = today.day
    first_day_curr = today.replace(day=1)
    last_day_prev = first_day_curr - pd.Timedelta(days=1)
    first_day_prev = last_day_prev.replace(day=1)
    period_str = first_day_prev.strftime('%Y-%m')
    
    try:
        enc_key = get_encryption_key()
        silae_conf = {k: get_secret(f"SILAE_{k.upper()}") for k in ["client_id", "client_secret", "subscription_key"]}
    except Exception as e:
        print(f"CRITIQUE: {e}")
        return

    if not DB: return
    try:
        clients = list(DB.collection("payflow_clients").where("jour_transfert", "==", current_day).stream())
    except: return

    if not clients:
        print("Rien à traiter.")
        return

    try:
        token = get_silae_token(silae_conf)
    except: return

    for doc in clients:
        data = doc.to_dict()
        name = data.get('nom', 'Inconnu')
        doc_id = doc.id
        email = data.get('odoo_login')
        
        print(f"Traitement: {name}")
        try:
            data['odoo_password'] = decrypt_data(data.get('odoo_password'), enc_key)
            ecritures = get_silae_ecritures(token, silae_conf, data['numero_dossier_silae'], first_day_prev, last_day_prev)
            status, msg = import_to_odoo_auto(data, ecritures, period_str, last_day_prev)
            log_execution(doc_id, name, period_str, status, msg)
            
            if status.startswith("ERROR"):
                send_error_email(email, name, period_str, msg)

        except Exception as e:
            err = str(e)
            log_execution(doc_id, name, period_str, "ERROR_CRASH", err)
            send_error_email(email, name, period_str, f"Crash: {err}")