import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()
account_sid = os.getenv('TWILIO_ACCOUNT_SID')
auth_token = os.getenv('TWILIO_AUTH_TOKEN')

print("1. Creating Content API Template via HTTP...")
url = f"https://content.twilio.com/v1/Content"
payload = {
    "friendly_name": "Test Quick Reply",
    "language": "en",
    "types": {
        "twilio/quick-reply": {
            "body": "Test: Do you see this button?",
            "actions": [
                {"title": "👍 Dashboard'a Gönder", "id": "1"}
            ]
        }
    }
}

res = requests.post(url, auth=(account_sid, auth_token), json=payload)
if res.status_code != 201:
    print(f"Failed to create content: {res.text}")
    exit(1)

content_sid = res.json()['sid']
print(f"Content SID: {content_sid}")

print("2. Sending message...")
msg_url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
msg_payload = {
    "From": "whatsapp:+14155238886",
    "To": "whatsapp:+905464055467",
    "ContentSid": content_sid
}

msg_res = requests.post(msg_url, auth=(account_sid, auth_token), data=msg_payload)
print(f"Message status: {msg_res.status_code}")
print(msg_res.text)
