from twilio.rest import Client
import os
from dotenv import load_dotenv

load_dotenv()
account_sid = os.getenv('TWILIO_ACCOUNT_SID')
auth_token = os.getenv('TWILIO_AUTH_TOKEN')
client = Client(account_sid, auth_token)

try:
    message = client.messages.create(
        from_='whatsapp:+14155238886',
        to='whatsapp:+905464055467',
        body="This is a test message.",
        persistent_action=['Send to Dashboard'] # this is not the right parameter, let's see what happens or what the docs say
    )
    print("Success")
except Exception as e:
    print(e)
