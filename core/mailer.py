"""
Email sending module for RapidSite AI
Supports SMTP providers like Gmail, SendGrid, etc.
"""
import os
import socket
import random
import traceback
from email.utils import parseaddr
from flask import current_app, render_template
from flask_mail import Mail, Message
from datetime import datetime, timedelta
import requests

mail = Mail()

def _configured_email_provider():
    """Return the configured email provider, inferring API providers when possible."""
    provider = (os.getenv('EMAIL_PROVIDER') or 'auto').strip().lower()
    if provider != 'auto':
        return provider
    if os.getenv('RESEND_API_KEY'):
        return 'resend'
    if os.getenv('SENDGRID_API_KEY'):
        return 'sendgrid'
    return 'smtp'

def _default_sender():
    return (
        os.getenv('EMAIL_FROM')
        or os.getenv('SMTP_FROM_EMAIL')
        or os.getenv('SMTP_USERNAME')
    )

def _missing_smtp_settings():
    """Return required SMTP settings that are not configured."""
    required = {
        'SMTP_USERNAME': os.getenv('SMTP_USERNAME'),
        'SMTP_PASSWORD': os.getenv('SMTP_PASSWORD'),
    }
    return [key for key, value in required.items() if not value]

def init_mail(app):
    """Initialize Flask-Mail with app configuration"""
    port_value = os.getenv('SMTP_PORT') or '587'
    try:
        port = int(port_value)
    except ValueError:
        app.logger.warning("Invalid SMTP_PORT %r; falling back to 587", port_value)
        port = 587
    
    app.config['MAIL_SERVER'] = os.getenv('SMTP_SERVER') or 'smtp.gmail.com'
    app.config['MAIL_PORT'] = port
    
    # Port 465 requires SSL, Port 587 requires TLS
    if port == 465:
        app.config['MAIL_USE_SSL'] = True
        app.config['MAIL_USE_TLS'] = False
    else:
        app.config['MAIL_USE_SSL'] = False
        app.config['MAIL_USE_TLS'] = True
        
    app.config['MAIL_USERNAME'] = os.getenv('SMTP_USERNAME') or None
    app.config['MAIL_PASSWORD'] = os.getenv('SMTP_PASSWORD') or None
    app.config['MAIL_DEFAULT_SENDER'] = _default_sender()
    
    # Set timeout low enough so that if SMTP is blocked (Render free tier),
    # it fails fast instead of hanging and causing a Gunicorn/Vercel 502 timeout.
    app.config['MAIL_TIMEOUT'] = 5  # 5 seconds timeout
    
    mail.init_app(app)
    return mail

def generate_verification_code():
    """Generate a 6-digit verification code"""
    return str(random.randint(100000, 999999))

def _send_with_smtp(subject: str, recipients: list[str], html: str):
    missing_settings = _missing_smtp_settings()
    if missing_settings:
        current_app.logger.error(
            "Cannot send email through SMTP. Missing settings: %s",
            ', '.join(missing_settings)
        )
        return False

    old_timeout = socket.getdefaulttimeout()
    try:
        socket.setdefaulttimeout(5.0)
        msg = Message(
            subject=subject,
            recipients=recipients
        )
        msg.html = html
        
        mail.send(msg)
        return True
    except Exception as e:
        current_app.logger.error(f"Failed to send email through SMTP: {e}")
        traceback.print_exc()
        return False
    finally:
        socket.setdefaulttimeout(old_timeout)

def _send_with_resend(subject: str, recipients: list[str], html: str):
    api_key = os.getenv('RESEND_API_KEY')
    sender = _default_sender()
    if not api_key or not sender:
        current_app.logger.error("Cannot send email through Resend. Missing RESEND_API_KEY or EMAIL_FROM.")
        return False

    try:
        response = requests.post(
            'https://api.resend.com/emails',
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            },
            json={
                'from': sender,
                'to': recipients,
                'subject': subject,
                'html': html,
            },
            timeout=10,
        )
        if response.status_code not in (200, 201):
            current_app.logger.error(
                "Resend email failed with status %s: %s",
                response.status_code,
                response.text[:500]
            )
            return False
        return True
    except requests.RequestException as e:
        current_app.logger.error(f"Failed to send email through Resend: {e}")
        return False

def _send_with_sendgrid(subject: str, recipients: list[str], html: str):
    api_key = os.getenv('SENDGRID_API_KEY')
    sender = _default_sender()
    sender_name = os.getenv('EMAIL_FROM_NAME') or 'RapidSite AI'
    sender_email = parseaddr(sender or '')[1]
    if not api_key or not sender_email:
        current_app.logger.error("Cannot send email through SendGrid. Missing SENDGRID_API_KEY or EMAIL_FROM.")
        return False

    try:
        response = requests.post(
            'https://api.sendgrid.com/v3/mail/send',
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            },
            json={
                'personalizations': [
                    {'to': [{'email': recipient} for recipient in recipients]}
                ],
                'from': {'email': sender_email, 'name': sender_name},
                'subject': subject,
                'content': [{'type': 'text/html', 'value': html}],
            },
            timeout=10,
        )
        if response.status_code != 202:
            current_app.logger.error(
                "SendGrid email failed with status %s: %s",
                response.status_code,
                response.text[:500]
            )
            return False
        return True
    except requests.RequestException as e:
        current_app.logger.error(f"Failed to send email through SendGrid: {e}")
        return False

def _send_email(subject: str, recipients: list[str], html: str):
    provider = _configured_email_provider()
    if provider == 'resend':
        return _send_with_resend(subject, recipients, html)
    if provider == 'sendgrid':
        return _send_with_sendgrid(subject, recipients, html)
    if provider == 'smtp':
        return _send_with_smtp(subject, recipients, html)

    current_app.logger.error("Unsupported EMAIL_PROVIDER: %s", provider)
    return False

def send_verification_email(email: str, code: str, company_name: str):
    """Send verification code email to user synchronously"""
    html = render_template(
        'emails/verification.html',
        company_name=company_name,
        code=code
    )
    return _send_email('Verify Your RapidSite AI Account', [email], html)

def send_password_reset_email(email: str, reset_link: str):
    """Send password reset email synchronously"""
    html = render_template(
        'emails/password_reset.html',
        reset_link=reset_link
    )
    return _send_email('Reset Your RapidSite AI Password', [email], html)
