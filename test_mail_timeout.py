import time
from flask import Flask
from flask_mail import Mail, Message

app = Flask(__name__)
app.config['MAIL_SERVER'] = '10.255.255.1'  # Unreachable IP
app.config['MAIL_PORT'] = 587
app.config['MAIL_TIMEOUT'] = 3  # 3 seconds
app.config['MAIL_DEFAULT_SENDER'] = 'test@test.com'

mail = Mail(app)

with app.app_context():
    msg = Message("Test", recipients=["test@test.com"])
    start = time.time()
    try:
        mail.send(msg)
    except Exception as e:
        print(f"Exception: {type(e).__name__}: {e}")
    end = time.time()
    print(f"Took: {end - start:.2f} seconds")
