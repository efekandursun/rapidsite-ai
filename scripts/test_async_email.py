import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from app import app
from core.mailer import send_verification_email
import threading

with app.app_context():
    print("Sending email via Flask-Mail async...")
    success = send_verification_email("efekan@rapidsite.app", "123456", "Test Company")
    print(f"Initiate Success: {success}")
    
    # Wait for all threads to finish to see if there is an error
    for t in threading.enumerate():
        if t is not threading.current_thread():
            print(f"Waiting for thread: {t.name}")
            t.join()
    print("Done waiting.")
