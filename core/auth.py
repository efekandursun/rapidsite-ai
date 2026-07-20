"""
RapidSite AI - Authentication Module
Handles user registration, login, and session management.
"""

import os
import re
import hashlib
import secrets
import bcrypt
from functools import wraps
from flask import Blueprint, request, render_template, redirect, url_for, session, flash

from core.database import Database

auth_bp = Blueprint('auth', __name__)
db = Database()


def hash_password(password: str) -> str:
    """Hash password using bcrypt (industry standard)."""
    # bcrypt handles salting automatically
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt(rounds=12)  # 12 rounds = good balance of security/performance
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')  # Store as string in database


def verify_password(password: str, password_hash: str) -> bool:
    """
    Verify password against hash.
    Only supports bcrypt. Legacy SHA-256 is deprecated for security reasons.
    """
    password_bytes = password.encode('utf-8')
    
    # Check if it's bcrypt hash (starts with $2b$ or $2a$)
    if password_hash.startswith('$2'):
        try:
            return bcrypt.checkpw(password_bytes, password_hash.encode('utf-8'))
        except Exception:
            return False
    else:
        # CRITICAL: Legacy SHA-256 fallback removed for security reasons.
        # Users with old hashes MUST reset their passwords.
        import logging
        logging.error("Attempted login with legacy SHA-256 hash. Login rejected for security. User must reset password.")
        return False


def login_required(f):
    """Decorator to require login for routes."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or not get_current_user():
            session.clear()
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


def get_current_user():
    """Get current logged-in user."""
    if 'user_id' in session:
        return db.get_user(session['user_id'])
    return None


def get_current_company():
    """Get current user's company."""
    user = get_current_user()
    if user and user.get('company_id'):
        return db.get_company(user['company_id'])
    return None


def slugify(text: str) -> str:
    """Convert text to URL-friendly slug."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[-\s]+', '-', text)
    return text


# =============================================================================
# AUTH ROUTES
# =============================================================================

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Login page."""
    if 'user_id' in session:
        if get_current_user():
            return redirect(url_for('dashboard'))
        else:
            session.clear()
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        
        if not email or not password:
            flash('Please enter email and password.', 'error')
            return render_template('auth/login.html')
        
        user = db.get_user_by_email(email)
        
        if user and verify_password(password, user['password_hash']):
            session.permanent = True
            session['user_id'] = user['id']
            session['company_id'] = user['company_id']
            session['user_name'] = user['name']
            session['user_email'] = user['email']
            
            flash(f'Welcome back, {user["name"]}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password.', 'error')
    
    return render_template('auth/login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Registration page for new companies."""
    if 'user_id' in session:
        if get_current_user():
            return redirect(url_for('dashboard'))
        else:
            session.clear()
    
    if request.method == 'POST':
        # Company info
        company_name = request.form.get('company_name', '').strip()
        
        # User info
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        # Validation
        errors = []
        
        if not company_name:
            errors.append('Company name is required.')
        if not name:
            errors.append('Your name is required.')
        if not email or '@' not in email:
            errors.append('Valid email is required.')
        if len(password) < 6:
            errors.append('Password must be at least 6 characters.')
        if password != confirm_password:
            errors.append('Passwords do not match.')
        
        # Check if email already exists
        if db.get_user_by_email(email):
            errors.append('Email already registered.')
        
        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template('auth/register.html')
        
        try:
            # Create company
            slug = slugify(company_name)
            # Make slug unique if needed
            base_slug = slug
            counter = 1
            while db.get_company_by_slug(slug):
                slug = f"{base_slug}-{counter}"
                counter += 1
            
            company_id = db.create_company(
                name=company_name,
                slug=slug
            )
            
            # Create user (admin role for first user, email NOT verified yet)
            user_id = db.create_user(
                email=email,
                password_hash=hash_password(password),
                name=name,
                company_id=company_id,
                role='admin'
            )
            
            # Generate and send verification code
            from core.mailer import generate_verification_code, send_verification_email
            from datetime import datetime, timedelta
            
            code = generate_verification_code()
            expires_at = (datetime.now() + timedelta(minutes=15)).isoformat()
            
            db.set_verification_code(email, code, expires_at)
            
            if send_verification_email(email, code, company_name):
                # Store email in session for verification page
                session['pending_verification_email'] = email
                flash('Registration successful! Please check your email for verification code.', 'success')
                return redirect(url_for('auth.verify_email'))
            else:
                flash('Registration successful, but failed to send verification email. Please contact support.', 'warning')
                return redirect(url_for('auth.login'))
        except Exception as e:
            flash(f'Registration failed: {str(e)}', 'error')
    
    return render_template('auth/register.html')


@auth_bp.route('/verify-email', methods=['GET', 'POST'])
def verify_email():
    """Email verification page."""
    email = session.get('pending_verification_email', '')
    
    if request.method == 'POST':
        form_email = request.form.get('email', '').strip().lower()
        code = request.form.get('code', '').strip()
        
        # Prefer form email over session email to allow manual entry
        verify_email_addr = form_email or email
        
        if not verify_email_addr:
            flash('Please enter your email address.', 'error')
            return render_template('auth/verify_email.html', email=verify_email_addr)
            
        if not code:
            flash('Please enter verification code.', 'error')
            return render_template('auth/verify_email.html', email=verify_email_addr)
        
        if db.verify_email(verify_email_addr, code):
            # Get user and auto-login
            user = db.get_user_by_email(verify_email_addr)
            if user:
                session.pop('pending_verification_email', None)
                session.permanent = True
                session['user_id'] = user['id']
                session['company_id'] = user['company_id']
                session['user_name'] = user['name']
                session['user_email'] = user['email']
                
                flash(f'Email verified! Welcome to RapidSite AI, {user["name"]}!', 'success')
                return redirect(url_for('dashboard'))
        else:
            flash('Invalid or expired verification code.', 'error')
    
    return render_template('auth/verify_email.html', email=email)


@auth_bp.route('/resend-verification', methods=['POST'])
def resend_verification():
    """Resend verification code with rate limiting."""
    email = session.get('pending_verification_email')
    
    if not email:
        flash('No pending verification found.', 'warning')
        return redirect(url_for('auth.login'))
    
    # Rate limiting: 60 seconds between resends
    from datetime import datetime, timedelta
    
    last_resend = session.get('last_resend_time')
    if last_resend:
        last_resend_dt = datetime.fromisoformat(last_resend)
        time_since_last = (datetime.now() - last_resend_dt).total_seconds()
        
        if time_since_last < 60:
            remaining = int(60 - time_since_last)
            flash(f'Please wait {remaining} seconds before requesting another code.', 'warning')
            return redirect(url_for('auth.verify_email'))
    
    try:
        from core.mailer import generate_verification_code, send_verification_email
        
        # Get user's company
        user = db.get_user_by_email(email)
        if not user:
            flash('User not found.', 'error')
            return redirect(url_for('auth.login'))
        
        company = db.get_company(user['company_id'])
        company_name = company['name'] if company else 'Your Company'
        
        code = generate_verification_code()
        expires_at = (datetime.now() + timedelta(minutes=15)).isoformat()
        
        db.set_verification_code(email, code, expires_at)
        
        if send_verification_email(email, code, company_name):
            # Update rate limit timestamp
            session['last_resend_time'] = datetime.now().isoformat()
            flash('Verification code resent! Please check your email.', 'success')
        else:
            flash('Failed to resend verification code.', 'error')
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
    
    return redirect(url_for('auth.verify_email'))



@auth_bp.route('/logout')
def logout():
    """Logout and clear session."""
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Handle forgot password requests."""
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        if not email:
            flash('Please enter your email address.', 'error')
            return redirect(url_for('auth.forgot_password'))
            
        # Security: Rate limiting to prevent email spam/bombing
        from datetime import datetime, timedelta
        last_reset = session.get('last_forgot_time')
        if last_reset:
            last_reset_dt = datetime.fromisoformat(last_reset)
            time_since = (datetime.now() - last_reset_dt).total_seconds()
            if time_since < 60:
                remaining = int(60 - time_since)
                flash(f'Please wait {remaining} seconds before requesting another reset.', 'warning')
                return redirect(url_for('auth.forgot_password'))
                
        user = db.get_user_by_email(email)
        if user:
            # Generate token
            token = secrets.token_urlsafe(32)
            # Expires in 15 mins
            from datetime import datetime, timedelta
            expires_at = (datetime.now() + timedelta(minutes=15)).isoformat()
            
            db.set_reset_token(email, token, expires_at)
            
            reset_link = request.host_url.rstrip('/') + url_for('auth.reset_password', token=token)
            from core.mailer import send_password_reset_email
            send_password_reset_email(email, reset_link)
            
        # Update rate limit timestamp
        session['last_forgot_time'] = datetime.now().isoformat()
            
        # Always show success message to prevent email enumeration attacks
        flash('If an account exists with that email, a password reset link has been sent.', 'success')
        return redirect(url_for('auth.login'))
        
    return render_template('auth/forgot_password.html')

@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Handle password reset via token."""
    user = db.get_user_by_reset_token(token)
    
    if not user:
        flash('Invalid or expired reset link. Please request a new one.', 'error')
        return redirect(url_for('auth.forgot_password'))
        
    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
            return render_template('auth/reset_password.html', token=token)
            
        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('auth/reset_password.html', token=token)
            
        db.update_password(user['id'], hash_password(password))
        
        flash('Your password has been successfully reset. Please log in.', 'success')
        return redirect(url_for('auth.login'))
        
    return render_template('auth/reset_password.html', token=token)

