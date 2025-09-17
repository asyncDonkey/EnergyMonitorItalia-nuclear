from flask import Flask, render_template
import firebase_admin
from firebase_admin import credentials, firestore
import os

# SETUP FLASK APP
app = Flask(__name__)

# Initialize Firestore DB
cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

# PRINCIPAL ROUTE
@app.route('/')
def dashboard():
    """
    Questa funzione viene eseguita quando un utente visita la pagina principale.
    Legge i risultati dall'ultimo calcolo salvato su Firestore e li passa
    a un template HTML per la visualizzazione.
    """
    try:
        #   Fetch the latest simulation results 
        results_ref = db.collection('simulation_results').document('latest')
        results = results_ref.get().to_dict()
        
        # Pass data to HTML template for rendering
        return render_template('index.html', data=results)
    except Exception as e:
        # If an error occurs (e.g., no data yet), show a message
        return f"Errore nel caricare i dati: {e}. Esegui prima lo script 'nuclear_analyzer.py'."

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)