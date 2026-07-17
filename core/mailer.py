"""
Email sending module for RapidSite AI
Supports SMTP providers like Gmail, SendGrid, etc.
"""
import os
import random
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
    app.config['MAIL_DEFAULT_SENDER'] = os.getenv('SMTP_USERNAME')
    
    # Prevent Gunicorn worker timeouts if SMTP server hangs
    app.config['MAIL_TIMEOUT'] = 5  # 5 seconds timeout
    
    mail.init_app(app)
    return mail

def generate_verification_code():
    """Generate a 6-digit verification code"""
    return str(random.randint(100000, 999999))

def send_verification_email(email: str, code: str, company_name: str):
    """Send verification code email to user"""
    try:
        msg = Message(
            subject='Verify Your RapidSite AI Account',
            recipients=[email]
        )
        
        msg.html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    background: #f3f4f6;
                    margin: 0;
                    padding: 20px;
                }}
                .container {{
                    max-width: 600px;
                    margin: 0 auto;
                    background: white;
                    border-radius: 12px;
                    overflow: hidden;
                    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                }}
                .header {{
                    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                    padding: 30px;
                    text-align: center;
                }}
                .logo {{
                    font-size: 24px;
                    font-weight: 700;
                    background: linear-gradient(90deg, #00d4ff, #7c3aed);
                    -webkit-background-clip: text;
                    -webkit-text-fill-color: transparent;
                }}
                .content {{
                    padding: 40px 30px;
                }}
                .code-box {{
                    background: #f3f4f6;
                    border: 2px dashed #3b82f6;
                    border-radius: 8px;
                    padding: 20px;
                    text-align: center;
                    margin: 30px 0;
                }}
                .code {{
                    font-size: 36px;
                    font-weight: 700;
                    color: #1a1a2e;
                    letter-spacing: 8px;
                    font-family: 'Monaco', 'Consolas', monospace;
                }}
                .footer {{
                    padding: 20px 30px;
                    background: #f9fafb;
                    text-align: center;
                    color: #6b7280;
                    font-size: 14px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <div class="logo">🏗️ RapidSite AI</div>
                </div>
                <div class="content">
                    <h2>Welcome to RapidSite AI!</h2>
                    <p>Hi there,</p>
                    <p>Thank you for registering <strong>{company_name}</strong> on RapidSite AI.</p>
                    <p>Please use the verification code below to complete your registration:</p>
                    
                    <div class="code-box">
                        <div class="code">{code}</div>
                    </div>
                    
                    <p style="color: #6b7280; font-size: 14px;">
                        This code will expire in 15 minutes.
                    </p>
                    <p style="color: #6b7280; font-size: 14px;">
                        If you didn't request this code, please ignore this email.
                    </p>
                </div>
                <div class="footer">
                    <p>RapidSite AI - Construction Report System</p>
                    <p>This is an automated message, please do not reply.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        mail.send(msg)
        return True
    except Exception as e:
        print(f"❌ Failed to send email: {e}")
        return False

def send_password_reset_email(email: str, reset_link: str):
    """Send password reset email (future feature)"""
    pass
