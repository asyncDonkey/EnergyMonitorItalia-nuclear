import config
import pandas as pd
from datetime import date, timedelta
import firebase_admin
from firebase_admin import credentials, firestore
import requests
from io import StringIO
from lxml import etree

# _SYSTEM.INIT
# Checking credentials and connecting to database.
try:
    cred = credentials.Certificate("serviceAccountKey.json")
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("... Firebase Connection      [OK]")
except Exception as e:
    print(f"... Firebase Connection      [FAIL]")
    print(f"[FATAL] Service Account Key error. Terminating. Details: {e}")
    db = None

# CONSTANTS.LOAD
COSTO_MEDIO_PUN_ITALIA_EUR_MWh = 110.0
COSTO_NUCLEARE_FRANCIA_EUR_MWh = 70.0
PERCENTUALE_NUCLEARE_NEL_MIX = 0.65

# MODULE.API_CONNECTOR
def get_entsoe_data(document_type, country_name, country_code, start_date, end_date):
    url = "https://web-api.tp.entsoe.eu/api"
    
    # Set domain parameter based on document type.
    domain_param = 'outBiddingZone_Domain' if document_type == 'A65' else 'in_Domain'

    params = {
        'securityToken': config.ENTSOE_API_TOKEN,
        'documentType': document_type, 'processType': 'A16',
        domain_param: country_code,
        'periodStart': start_date, 'periodEnd': end_date
    }
    print(f">>> Requesting data for {country_name} [{document_type}]...")
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        root = etree.fromstring(response.content)
        ns = {'ns': 'urn:iec62325.351:tc57wg16:451-6:generationloaddocument:3:0'}
        
        # Check for API error messages in XML response.
        if root.find('.//ns:Reason', namespaces=ns) is not None:
            raise ValueError(root.find('.//ns:Reason/ns:text', namespaces=ns).text)

        all_records = []
        for time_series in root.findall('.//ns:TimeSeries', namespaces=ns):
            psr_type_node = time_series.find('.//ns:MktPSRType/ns:psrType', namespaces=ns)
            psr_type = psr_type_node.text if psr_type_node is not None else 'TotalLoad'

            for point in time_series.findall('.//ns:Point', namespaces=ns):
                all_records.append({
                    'position': int(point.find('ns:position', namespaces=ns).text),
                    'quantity_MW': float(point.find('ns:quantity', namespaces=ns).text),
                    'psrType': psr_type
                })
        
        if not all_records: raise ValueError("XML empty or invalid.")
        print(f"... Download complete for {country_name}. [OK]")
        return all_records
    except Exception as e:
        print(f"... Download failed for {country_name}.   [ERROR] > {e}")
        return []

# MODULE.DATABASE_IO
def save_data_to_firestore(collection, doc_id, data):
    if not db: raise ConnectionError("Firestore connection lost.")
    if not data:
        print(f"[WARN] No data to write for {collection}/{doc_id}. Skipping.")
        return
    doc_ref = db.collection(collection).document(doc_id)
    doc_ref.set({'records': data, 'updated_at': firestore.SERVER_TIMESTAMP}, merge=True)
    print(f"... Data committed to Firestore: {collection}/{doc_id}. [OK]")

# MODULE.SIMULATOR
def run_italian_simulation(load_records):
    pun_usato = COSTO_MEDIO_PUN_ITALIA_EUR_MWh

    df = pd.DataFrame(load_records)
    if df.empty:
        print("[SIM_ERROR] Cannot run simulation. Italian load data is empty.")
        return {}
        
    df['quantity_MW'] = pd.to_numeric(df['quantity_MW'])
    total_mwh = df['quantity_MW'].sum()
    
    costo_attuale = total_mwh * pun_usato
    costo_simulato = (total_mwh * PERCENTUALE_NUCLEARE_NEL_MIX * COSTO_NUCLEARE_FRANCIA_EUR_MWh) + \
                     (total_mwh * (1 - PERCENTUALE_NUCLEARE_NEL_MIX) * pun_usato)
    risparmio_totale = costo_attuale - costo_simulato
    
    return {
        "pun_usato_eur_mwh": pun_usato,
        "data_analisi": (date.today() - timedelta(days=2)).strftime('%Y-%m-%d'),
        "fabbisogno_mwh": total_mwh, "costo_attuale_eur": costo_attuale,
        "costo_simulato_eur": costo_simulato, "risparmio_giornaliero_eur": risparmio_totale,
        "risparmio_percentuale": (risparmio_totale / costo_attuale) * 100 if costo_attuale > 0 else 0,
        "risparmio_annuale_italia_eur": risparmio_totale * 365,
        "risparmio_annuale_famiglia_eur": (risparmio_totale * 365) / 25_000_000
    }

# MODULE.REPORT_GENERATOR
def print_report(results):
    if not results: return
    
    annual_savings_b = results.get('risparmio_annuale_italia_eur', 0) / 1_000_000_000
    family_savings = results.get('risparmio_annuale_famiglia_eur', 0)
    analysis_date = results.get('data_analisi', 'N/A')

    print("\n\n")
    print("+------------------------------------------------------+")
    print("|                                                      |")
    print("|   *** SIMULAZIONE NUCLEARE ITALIA - REPORT FINALE *** |")
    print("|                                                      |")
    print(f"|   DATA DI ANALISI: {analysis_date}                     |")
    print("+------------------------------------------------------+")
    print("| PARAMETRO                    | VALORE STIMATO        |")
    print("+------------------------------+-----------------------+")
    print(f"| Risparmio Annuale (Italia)   | EUR {annual_savings_b:>7.2f} Miliardi |")
    print(f"| Risparmio Annuale (Famiglia) | EUR {family_savings:>10.2f}       |")
    print("+------------------------------+-----------------------+")
    print("\n[EOT] - End Of Transmission")


# MAIN.EXECUTION_BLOCK
if __name__ == "__main__":
    if not db: exit()
    try:
        target_date = date.today() - timedelta(days=2)
        target_date_id = target_date.strftime('%Y-%m-%d')
        start_str = target_date.strftime('%Y%m%d0000')
        end_str = (target_date + timedelta(days=1)).strftime('%Y%m%d0000')
        
        print("\n[PROC_START] Initiating data fetch sequence...")
        # Fetching Italy Load (A65)
        load_data_it = get_entsoe_data('A65', 'Italy (Load)', '10YIT-GRTN-----B', start_str, end_str)
        save_data_to_firestore('daily_load_italy', target_date_id, load_data_it)
        
        # Fetching Generation Mixes (A75)
        countries = {
            'Italy (Generation)': '10YIT-GRTN-----B',
            'France': '10YFR-RTE------C',
            'Spain': '10YES-REE------0'
        }
        for name, code in countries.items():
            generation_data = get_entsoe_data('A75', name, code, start_str, end_str)
            save_data_to_firestore(f'daily_generation_{name.split(" ")[0].lower()}', target_date_id, generation_data)

        # FINAL ANALYSIS
        print("\n[PROC] Running simulation...")
        risultati_simulazione = run_italian_simulation(load_data_it)
        save_data_to_firestore('simulation_results', 'latest_italy', risultati_simulazione)
        
        if risultati_simulazione:
             print_report(risultati_simulazione)
        else:
             print("[WARN] Simulation produced no results. Report skipped.")

    except Exception as e:
        print(f"\n[CRITICAL] Main execution failed. Aborting. Details: {e}")