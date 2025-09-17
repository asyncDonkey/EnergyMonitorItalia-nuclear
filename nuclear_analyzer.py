import requests
import config
import pandas as pd
from datetime import date, timedelta
import firebase_admin
from firebase_admin import credentials, firestore

# FIREBASE SETUP
try:
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("✅ Connessione a Firestore stabilita.")
except Exception as e:
    print("❌ ERRORE: Assicurati che 'serviceAccountKey.json' sia presente e corretto.")
    db = None

# SIMULATION PARAMETERS
COSTO_MEDIO_PUN_ITALIA_EUR_MWh = 110.0
COSTO_NUCLEARE_FRANCIA_EUR_MWh = 70.0
PERCENTUALE_NUCLEARE_NEL_MIX = 0.65

# TERNA API FUNCTIONS
def get_access_token(client_id, client_secret):
    url = "https://api.terna.it/transparency/oauth/accessToken"
    payload = {'grant_type': 'client_credentials', 'client_id': client_id, 'client_secret': client_secret}
    print("1. Ottenimento token di accesso Terna...")
    response = requests.post(url, data=payload)
    response.raise_for_status()
    print("✅ Token ottenuto!")
    return response.json().get('access_token')

def get_total_load_for_yesterday(access_token):
    data_url = "https://api.terna.it/load/v2.0/total-load"
    yesterday = date.today() - timedelta(days=1)
    date_str = yesterday.strftime('%d/%m/%Y')
    params = {'dateFrom': date_str, 'dateTo': date_str}
    headers = {'Authorization': f'Bearer {access_token}'}
    print(f"2. Download del fabbisogno energetico italiano per il {date_str}...")
    response = requests.get(data_url, headers=headers, params=params)
    response.raise_for_status()
    records = response.json().get('total_load', [])
    print("✅ Dati scaricati!")
    return records

# DB AND ANALYSIS FUNCTIONS
def save_and_get_data(records):
    """Salva i dati su Firestore e li restituisce come DataFrame filtrato per 'Italy'."""
    if not db:
        raise ConnectionError("Connessione a Firestore non disponibile.")
    
    yesterday_doc_id = (date.today() - timedelta(days=1)).strftime('%Y-%m-%d')
    
    doc_ref = db.collection('daily_load_archive').document(yesterday_doc_id)
    doc_ref.set({'records': records})
    print(f"✅ Dati archiviati su Firestore in 'daily_load_archive/{yesterday_doc_id}'")
    
    italy_data = [rec for rec in records if rec['bidding_zone'] == 'Italy']
    if not italy_data:
        raise ValueError("Nessun dato trovato per la zona 'Italy' nei dati scaricati.")
    
    df = pd.DataFrame(italy_data)
    
    # Convert the column to numeric type before using it.
    df['total_load_MW'] = pd.to_numeric(df['total_load_MW'])
    
    return df

def run_simulation(df_load):
    print("\n3. Inizio analisi e simulazione...")
    total_mwh_giornaliero = df_load['total_load_MW'].sum() / 4
    costo_totale_attuale = total_mwh_giornaliero * COSTO_MEDIO_PUN_ITALIA_EUR_MWh
    mwh_da_nucleare = total_mwh_giornaliero * PERCENTUALE_NUCLEARE_NEL_MIX
    mwh_da_altro = total_mwh_giornaliero * (1 - PERCENTUALE_NUCLEARE_NEL_MIX)
    costo_nucleare = mwh_da_nucleare * COSTO_NUCLEARE_FRANCIA_EUR_MWh
    costo_altro = mwh_da_altro * COSTO_MEDIO_PUN_ITALIA_EUR_MWh
    costo_totale_simulato = costo_nucleare + costo_altro
    risparmio_totale = costo_totale_attuale - costo_totale_simulato
    risparmio_percentuale = (risparmio_totale / costo_totale_attuale) * 100
    risparmio_annuale_stimato = risparmio_totale * 365
    risparmio_annuale_famiglia = risparmio_annuale_stimato / 25_000_000
    return {
        "data_analisi": (date.today() - timedelta(days=1)).strftime('%Y-%m-%d'),
        "fabbisogno_mwh": total_mwh_giornaliero, "costo_attuale_eur": costo_totale_attuale,
        "costo_simulato_eur": costo_totale_simulato, "risparmio_giornaliero_eur": risparmio_totale,
        "risparmio_percentuale": risparmio_percentuale, "risparmio_annuale_italia_eur": risparmio_annuale_stimato,
        "risparmio_annuale_famiglia_eur": risparmio_annuale_famiglia
    }

def save_results_to_firestore(results):
    """Salva il dizionario dei risultati finali in un'apposita collezione su Firestore."""
    if not db:
        raise ConnectionError("Connessione a Firestore non disponibile.")
    
    # Use the 'latest' as a fixed ID to always have the latest result available
    doc_ref = db.collection('simulation_results').document('latest')
    doc_ref.set(results)
    print("✅ Risultati della simulazione salvati su Firestore in 'simulation_results/latest'")

def print_report(results):
    print("\n--- 📊 REPORT SIMULAZIONE NUCLEARE ---")
    print(f"Data di riferimento: {results['data_analisi']}")
    print("-" * 40)
    print(f"Fabbisogno energetico totale: {results['fabbisogno_mwh']:,.0f} MWh")
    print(f"Costo stimato attuale:         € {results['costo_attuale_eur']:,.2f}")
    print(f"Costo simulato con nucleare:    € {results['costo_simulato_eur']:,.2f}")
    print("-" * 40)
    print(f"💰 Risparmio giornaliero: € {results['risparmio_giornaliero_eur']:,.2f} ({results['risparmio_percentuale']:.2f}%)")
    print("\n--- 📈 PROIEZIONE ANNUALE ---")
    print(f"🇮🇹 Risparmio annuale stimato per l'Italia: € {results['risparmio_annuale_italia_eur']/1_000_000_000:.2f} miliardi")
    print(f"👨‍👩‍👧‍👦 Risparmio annuale stimato per famiglia:  € {results['risparmio_annuale_famiglia_eur']:.2f}")
    print("-" * 40)

# EXECUTION
if __name__ == "__main__":
    if not db:
        exit()
    try:
        token = get_access_token(config.CLIENT_ID, config.CLIENT_SECRET)
        total_load_records = get_total_load_for_yesterday(token)
        df_carico_italia = save_and_get_data(total_load_records)
        risultati = run_simulation(df_carico_italia)
        
        # Save results to Firestore before printing the report
        save_results_to_firestore(risultati)
        
        print_report(risultati)
        
    except Exception as e:
        print(f"\n❌ ERRORE durante l'esecuzione: {e}")
