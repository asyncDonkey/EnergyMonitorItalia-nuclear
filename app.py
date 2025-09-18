from flask import Flask, render_template
import firebase_admin
from firebase_admin import credentials, firestore
import os

# SETUP FLASK APP
app = Flask(__name__)

# Initialize Firestore DB
try:
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("Firestore connection established for Flask server.")
except Exception as e:
    print(f"CRITICAL ERROR: Unable to initialize Firebase for Flask: {e}")
    db = None


# PRINCIPAL ROUTE
@app.route('/')
def dashboard():
    try:
        results_ref = db.collection('simulation_results').document('latest_italy')
        results_doc = results_ref.get()

        if results_doc.exists:
            # Raw data from Firestore
            firestore_data = results_doc.to_dict()
            
            # Extract dictionary inside 'records'
            results = firestore_data.get('records', {})     
        else:
            results = {}
        
        # Pass data to the template
        return render_template('index.html', data=results)
        
    except Exception as e:
        return f"Error loading data: {e}. Please run the 'nuclear_analyzer.py' script first."

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)