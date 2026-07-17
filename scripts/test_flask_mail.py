import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from app import app
from core.mailer import send_verification_email

with app.app_context():
    print("Sending email via Flask-Mail...")
    success = send_verification_email("efekan@rapidsite.app", "123456", "Test Company")
    print(f"Success: {success}")
