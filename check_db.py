#DEBUG Script to check Firestore connection and document retrieval

import firebase_admin
from firebase_admin import credentials, firestore
import os

# Make shure the document path matches the one used in app.py

KEY_FILE = "serviceAccountKey.json"

print(f"Diagnostic Script Started")
print(f"Looking for key file: '{KEY_FILE}'...")

if not os.path.exists(KEY_FILE):
    print(f"FATAL ERROR: Key File '{KEY_FILE}' couldn't be found in this directory.")
    exit()

try:
    # Init Firebase
    cred = credentials.Certificate(KEY_FILE)
    # Check if an app is already initialized to avoid errors
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)

    db = firestore.client()
    print(f"Successfully connected to Firebase for the project: {cred.project_id}")

    # Exact query used by the Flask server
    collection_id = 'simulation_results'
    document_id = 'latest_italy'
    print(f"Looking for the document: '{collection_id}/{document_id}'...")

    doc_ref = db.collection(collection_id).document(document_id)
    doc = doc_ref.get()

    if doc.exists:
        print("\nDOCUMENT FOUND! Here is the content:")
        print("-----------------------------------------")
        # Print data in a readable format
        import json
        print(json.dumps(doc.to_dict(), indent=2))
        print("-----------------------------------------")
    else:
        print("\nERROR: Document not found!")
        print("This is why your web page is not showing data.")

except Exception as e:
    print(f"\nERROR DURING CONNECTION OR READING: {e}")

print("--- END OF DIAGNOSTIC ---")