"""
Email sending module for RapidSite AI
Supports SMTP providers like Gmail, SendGrid, etc.
"""
import os
import random
from threading import Thread
from flask import current_app, render_template
from flask_mail import Mail, Message
from datetime import datetime, timedelta

mail = Mail()

def init_mail(app):
    """Initialize Flask-Mail with app configuration"""
    port = int(os.getenv('SMTP_PORT', 587))
    
    app.config['MAIL_SERVER'] = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
    app.config['MAIL_PORT'] = port
    
    # Port 465 requires SSL, Port 587 requires TLS
    if port == 465:
        app.config['MAIL_USE_SSL'] = True
        app.config['MAIL_USE_TLS'] = False
    else:
        app.config['MAIL_USE_SSL'] = False
        app.config['MAIL_USE_TLS'] = True
        
    app.config['MAIL_USERNAME'] = os.getenv('SMTP_USERNAME')
    app.config['MAIL_PASSWORD'] = os.getenv('SMTP_PASSWORD')
    app.config['MAIL_DEFAULT_SENDER'] = os.getenv('SMTP_FROM_EMAIL', os.getenv('SMTP_USERNAME'))
    
    # Render free tier has slower network, need generous timeout
    app.config['MAIL_TIMEOUT'] = 60  # 60 seconds timeout
    
    mail.init_app(app)
    return mail

def generate_verification_code():
    """Generate a 6-digit verification code"""
    return str(random.randint(100000, 999999))

def send_async_email(app, msg):
    """Send email asynchronously in a background thread"""
    with app.app_context():
        try:
            mail.send(msg)
        except Exception as e:
            app.logger.error(f"Failed to send email: {e}")

def send_verification_email(email: str, code: str, company_name: str):
    """Send verification code email to user asynchronously"""
    try:
        app = current_app._get_current_object()
        msg = Message(
            subject='Verify Your RapidSite AI Account',
            recipients=[email]
        )
        
        msg.html = render_template(
            'emails/verification.html',
            company_name=company_name,
            code=code
        )
        
        Thread(target=send_async_email, args=(app, msg)).start()
        return True
    except Exception as e:
        current_app.logger.error(f"Failed to initiate verification email: {e}")
        return False

def send_password_reset_email(email: str, reset_link: str):
    """Send password reset email asynchronously"""
    try:
        app = current_app._get_current_object()
        msg = Message(
            subject='Reset Your RapidSite AI Password',
            recipients=[email]
        )
        
        msg.html = render_template(
            'emails/password_reset.html',
            reset_link=reset_link
        )
        
        Thread(target=send_async_email, args=(app, msg)).start()
        return True
    except Exception as e:
        current_app.logger.error(f"Failed to initiate password reset email: {e}")
        return False
