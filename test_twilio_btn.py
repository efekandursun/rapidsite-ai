from twilio.rest import Client
import os
from dotenv import load_dotenv
load_dotenv()

account_sid = os.environ['TWILIO_ACCOUNT_SID']
auth_token = os.environ['TWILIO_AUTH_TOKEN']
client = Client(account_sid, auth_token)

try:
    message = client.messages.create(
        body="Does this button work?",
        from_='whatsapp:' + os.environ['TWILIO_WHATSAPP_NUMBER'],
        to='whatsapp:+905389657685', # A fake number just to see if it throws an error building the payload
        # wait, how do I pass buttons? 
    )
    print("Success")
except Exception as e:
    print("Error:", e)
