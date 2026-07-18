"""
Email sending module for RapidSite AI
Supports SMTP providers like Gmail, SendGrid, etc.
"""
import os
import socket
import random
import traceback
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
    
    # Set timeout low enough so that if SMTP is blocked (Render free tier),
    # it fails fast instead of hanging and causing a Gunicorn/Vercel 502 timeout.
    app.config['MAIL_TIMEOUT'] = 5  # 5 seconds timeout
    
    mail.init_app(app)
    return mail

def generate_verification_code():
    """Generate a 6-digit verification code"""
    return str(random.randint(100000, 999999))

def send_verification_email(email: str, code: str, company_name: str):
    """Send verification code email to user synchronously"""
    old_timeout = socket.getdefaulttimeout()
    try:
        socket.setdefaulttimeout(30.0)
        msg = Message(
            subject='Verify Your RapidSite AI Account',
            recipients=[email]
        )
        
        msg.html = render_template(
            'emails/verification.html',
            company_name=company_name,
            code=code
        )
        
        mail.send(msg)
        return True
    except Exception as e:
        current_app.logger.error(f"Failed to send verification email: {e}")
        traceback.print_exc()
        return False
    finally:
        socket.setdefaulttimeout(old_timeout)

def send_password_reset_email(email: str, reset_link: str):
    """Send password reset email synchronously"""
    old_timeout = socket.getdefaulttimeout()
    try:
        socket.setdefaulttimeout(30.0)
        msg = Message(
            subject='Reset Your RapidSite AI Password',
            recipients=[email]
        )
        
        msg.html = render_template(
            'emails/password_reset.html',
            reset_link=reset_link
        )
        
        mail.send(msg)
        return True
    except Exception as e:
        current_app.logger.error(f"Failed to send password reset email: {e}")
        traceback.print_exc()
        return False
    finally:
        socket.setdefaulttimeout(old_timeout)
