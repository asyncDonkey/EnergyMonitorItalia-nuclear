import requests
import config
import pandas as pd
from datetime import date, timedelta
import firebase_admin
from firebase_admin import credentials, firestore
from io import StringIO
import time # Import time for a delay
from lxml import etree

# --- SETUP FIREBASE ---
try:
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("Connection to Firestore established.")
except Exception as e:
    print(f"ERROR: Please ensure 'serviceAccountKey.json' is present and correct.")
    db = None

# --- CONSTANTS ---
COSTO_MEDIO_PUN_ITALIA_EUR_MWh = 110.0
COSTO_NUCLEARE_FRANCIA_EUR_MWh = 70.0
PERCENTUALE_NUCLEARE_NEL_MIX = 0.65

# --- API FUNCTIONS ---
def get_access_token(client_id, client_secret):
    url = "https://api.terna.it/transparency/oauth/accessToken"
    payload = {'grant_type': 'client_credentials', 'client_id': client_id, 'client_secret': client_secret}
    print("1. Obtaining a Terna access token...")
    response = requests.post(url, data=payload)
    response.raise_for_status()
    print("Terna token obtained!")
    return response.json().get('access_token')

def get_terna_data_for_yesterday(access_token):
    data_url = "https://api.terna.it/load/v2.0/total-load"
    yesterday = date.today() - timedelta(days=1)
    date_str = yesterday.strftime('%d/%m/%Y')
    params = {'dateFrom': date_str, 'dateTo': date_str}
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Ocp-Apim-Subscription-Key': config.CLIENT_ID
    }
    print(f"2. Download Terna data for {date_str}...")
    response = requests.get(data_url, headers=headers, params=params)
    response.raise_for_status()
    print("Terna Data doownloaded!")
    return response.json().get('total_load', [])

# --- FUNZIONE ENTSO-E AGGIORNATA ---
def get_entsoe_generation_data(country_name, country_code, start_date, end_date):
    
    url = "https://web-api.tp.entsoe.eu/api"
    params = {
        'securityToken': config.ENTSOE_API_TOKEN,
        'documentType': 'A75',
        'processType': 'A16',
        'in_Domain': country_code,
        'periodStart': start_date, 'periodEnd': end_date
    }
    print(f"3. Download ENERGY MIX for {country_name}...")
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        # Usiamo lxml per analizzare il testo della risposta
        root = etree.fromstring(response.content)
        
        # Definiamo il namespace, che è come l'indirizzo ufficiale dei tag XML
        ns = {'ns': 'urn:iec62325.351:tc57wg16:451-6:generationloaddocument:3:0'}
        
        # Controlliamo se la risposta è un messaggio di errore
        reason_node = root.find('.//ns:Reason', namespaces=ns)
        if reason_node is not None:
            reason_text = reason_node.find('.//ns:text', namespaces=ns).text
            raise Exception(f"API returned an error: {reason_text}")

        all_records = []
        # Iteriamo su ogni "blocco" TimeSeries, che rappresenta una fonte energetica
        for time_series in root.findall('.//ns:TimeSeries', namespaces=ns):
            psr_type_node = time_series.find('.//ns:MktPSRType/ns:psrType', namespaces=ns)
            if psr_type_node is None:
                continue
            
            psr_type = psr_type_node.text
            
            # Per ogni fonte, iteriamo sui suoi "Point" (le misurazioni orarie)
            for point in time_series.findall('.//ns:Point', namespaces=ns):
                position = int(point.find('ns:position', namespaces=ns).text)
                quantity = float(point.find('ns:quantity', namespaces=ns).text)
                
                all_records.append({
                    'position': position,
                    'quantity_MW': quantity,
                    'psrType': psr_type
                })
        
        if not all_records:
            raise Exception("The XML document does not contain valid production data.")

        print(f"Data for {country_name} downloaded!")
        return all_records

    except Exception as e:
        print(f"Error downloading data for: {country_name}: {e}")
        return []

    

# --- DATABASE & ANALYSIS FUNCTIONS ---
def save_data_to_firestore(collection, doc_id, data):
    if not db: raise ConnectionError("Firestore not connected.")
    if not data:
        print(f"No data to save for {collection}/{doc_id}.")
        return
    doc_ref = db.collection(collection).document(doc_id)
    doc_ref.set({'records': data, 'updated_at': firestore.SERVER_TIMESTAMP}, merge=True)
    print(f"Data saved on Firestore in '{collection}/{doc_id}'")

def run_italian_simulation(records):
    df = pd.DataFrame([r for r in records if r['bidding_zone'] == 'Italy'])
    if df.empty:
        print("(!) No data for the 'Italy' zone was found for the simulation.")
        return {}
    df['total_load_MW'] = pd.to_numeric(df['total_load_MW'])
    total_mwh = df['total_load_MW'].sum() / 4
    costo_attuale = total_mwh * COSTO_MEDIO_PUN_ITALIA_EUR_MWh
    costo_simulato = (total_mwh * PERCENTUALE_NUCLEARE_NEL_MIX * COSTO_NUCLEARE_FRANCIA_EUR_MWh) + \
                     (total_mwh * (1 - PERCENTUALE_NUCLEARE_NEL_MIX) * COSTO_MEDIO_PUN_ITALIA_EUR_MWh)
    risparmio_totale = costo_attuale - costo_simulato
    return {
        "data_analisi": (date.today() - timedelta(days=1)).strftime('%Y-%m-%d'),
        "fabbisogno_mwh": total_mwh, "costo_attuale_eur": costo_attuale,
        "costo_simulato_eur": costo_simulato, "risparmio_giornaliero_eur": risparmio_totale,
        "risparmio_percentuale": (risparmio_totale / costo_attuale) * 100 if costo_attuale > 0 else 0,
        "risparmio_annuale_italia_eur": risparmio_totale * 365,
        "risparmio_annuale_famiglia_eur": (risparmio_totale * 365) / 25_000_000
    }

def print_report(results):
    if not results: return
    print("\n--- NUCLEAR SIMULATION REPORT ITALY ---")
    print(f"Estimated annual savings for Italy: € {results.get('risparmio_annuale_italia_eur', 0)/1_000_000_000:.2f} billions")
    print(f"Estimated annual savings per family:  € {results.get('risparmio_annuale_famiglia_eur', 0):.2f}")
    print("-" * 45)

# MAIN EXECUTION
if __name__ == "__main__":
    if not db: exit()
    try:
        # ITALY DATA
        terna_token = get_access_token(config.CLIENT_ID, config.CLIENT_SECRET)
        time.sleep(1)
        load_data_it = get_terna_data_for_yesterday(terna_token)
        yesterday_id = (date.today() - timedelta(days=1)).strftime('%Y-%m-%d')
        save_data_to_firestore('daily_load_italy', yesterday_id, load_data_it)
        
        # EU DATA
        target_date = date.today() - timedelta(days=2)
        target_date_id = target_date.strftime('%Y-%m-%d')
        start_str = target_date.strftime('%Y%m%d0000')
        end_str = (target_date + timedelta(days=1)).strftime('%Y%m%d0000')
        
        # FRANCE
        generation_data_fr = get_entsoe_generation_data('France', '10YFR-RTE------C', start_str, end_str)
        save_data_to_firestore('daily_generation_france', target_date_id, generation_data_fr)
        
        # SPAIN 
        generation_data_es = get_entsoe_generation_data('Spain', '10YES-REE------0', start_str, end_str)
        save_data_to_firestore('daily_generation_spain', target_date_id, generation_data_es)

        # ANALYSIS & REPORT (CORRECTED)
        print("\n4. Running simulation analyses for Italy...")
        risultati_simulazione = run_italian_simulation(load_data_it)

        # Always save the result to Firestore to reflect the latest run
        save_data_to_firestore('simulation_results', 'latest_italy', risultati_simulazione)

        # Only print the report if there are results to show
        if risultati_simulazione:
            print_report(risultati_simulazione)

    except Exception as e:
        print(f"\nERROR while running: {e}")