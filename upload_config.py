import json
import firebase_admin
from firebase_admin import credentials, firestore

# Initialize Firebase
cred = credentials.Certificate("firebase_key.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

def upload_json_to_firestore(json_file, collection_name, doc_id):
    """
    Uploads a JSON file to a specific document in a Firestore collection.
    """
    with open(json_file, 'r') as f:
        data = json.load(f)
    
    if doc_id:
        doc_ref = db.collection(collection_name).document(doc_id)
        doc_ref.set(data)
        print(f"Uploaded {json_file} to document '{doc_id}' in collection '{collection_name}'.")
    else:
        for key, value in data.items():
            doc_ref = db.collection(collection_name).document(key)
            doc_ref.set(value)
        print(f"Uploaded {json_file} to collection '{collection_name}'.")


if __name__ == "__main__":
    # Upload settings.json
    upload_json_to_firestore('settings.json', 'config', 'settings')
    # Upload events.json
    upload_json_to_firestore('events.json', 'config', 'events')
    # Upload cosmetics.json
    upload_json_to_firestore('cosmetics.json', 'config', 'cosmetics')
    # Upload items.json
    upload_json_to_firestore('items.json', 'config', 'items')
