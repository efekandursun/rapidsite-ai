import os
from dotenv import load_dotenv
from connectors.procore import ProcoreConnector
from core.database import Database

load_dotenv()

db = Database()
# Get a token from db (we'll just use any active token, maybe the last one created)
with db.get_connection() as conn:
    c = db._execute(conn, "SELECT access_token, refresh_token FROM users WHERE procore_connected = true LIMIT 1")
    user = c.fetchone()

if user:
    procore = ProcoreConnector()
    procore.access_token = user['access_token']
    procore.refresh_token = user['refresh_token']
    procore._authenticated = True
    
    # We need company_id
    companies = procore.get_companies()
    if companies:
        procore.company_id = companies[0]['id']
        print(f"Using company: {procore.company_id}")
        
        # Test creating vendor
        import requests
        url = f"{procore.base_url}/rest/v1.0/vendors"
        payload = {
            "company_id": procore.company_id,
            "vendor": {
                "name": "FieldFlow Test Vendor"
            }
        }
        resp = requests.post(url, headers=procore.headers, json=payload)
        print(resp.status_code)
        print(resp.text)
else:
    print("No authenticated user found.")
