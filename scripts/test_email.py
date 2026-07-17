import os
import sys
import smtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
load_dotenv(os.path.join(PROJECT_ROOT, '.env'))

server = os.getenv('SMTP_SERVER')
port = int(os.getenv('SMTP_PORT', 587))
username = os.getenv('SMTP_USERNAME')
password = os.getenv('SMTP_PASSWORD')
from_email = os.getenv('SMTP_FROM_EMAIL', username)
to_email = username # Send to self for testing

msg = MIMEText("Test email from FieldFlow AI")
msg['Subject'] = 'Test Email'
msg['From'] = from_email
msg['To'] = to_email

print(f"Connecting to {server}:{port}...")
try:
    with smtplib.SMTP(server, port) as smtp:
        smtp.set_debuglevel(1)
        smtp.starttls()
        print(f"Logging in as {username}...")
        smtp.login(username, password)
        print("Sending...")
        smtp.send_message(msg)
        print("Success!")
except Exception as e:
    print(f"Error: {e}")
