import os
import requests
from dotenv import load_dotenv
from core.database import Database
from connectors.procore import ProcoreConnector
from datetime import datetime

load_dotenv()

# Get token from DB
db = Database()
with db.get_connection() as conn:
    cursor = db._execute(conn, "SELECT procore_access_token, procore_default_project_id FROM companies LIMIT 1")
    row = db._fetchone(cursor)
    
token = row['procore_access_token']
project_id = row['procore_default_project_id']

print(f"Project ID: {project_id}")

connector = ProcoreConnector({"access_token": token, "use_sandbox": True})
connector.company_id = 987654 # Replace dynamically if needed, but we can just let it fetch?
# wait, ProcoreConnector fetches company_id in _authenticated, let's just use it
connector.authenticate()

log_data = {
    "log_type": "delivery",
    "item": "Cement",
    "quantity": 250,
    "unit": "tons",
    "description": "A kapısına 250 ton çimento geldi",
    "delivery_details": {
        "delivery_from": "Vendor ABC",
        "tracking_number": ""
    }
}

print("Pushing delivery log...")
try:
    log_date = datetime.utcnow().strftime("%Y-%m-%d")
    endpoint, payload, category_label = connector._build_category_payload("delivery", log_data, log_date)
    
    url = f"{connector.base_url}/rest/v1.0/projects/{project_id}/{endpoint}"
    print(f"URL: {url}")
    print(f"Payload: {payload}")
    
    headers = connector.headers.copy()
    if connector.company_id:
        headers["Procore-Company-Id"] = str(connector.company_id)
        
    response = requests.post(url, headers=headers, json=payload)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")
    
except Exception as e:
    print(f"Error: {e}")
