import os
import json
import logging
import hmac
import hashlib
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, jsonify, request, render_template, redirect, url_for, session, flash
from flask_cors import CORS
from dotenv import load_dotenv
import rq_dashboard
from flask_wtf.csrf import CSRFProtect

load_dotenv()

import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration

SENTRY_DSN = os.getenv("SENTRY_DSN")
if SENTRY_DSN and SENTRY_DSN != "your_sentry_dsn_here":
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[FlaskIntegration()],
        traces_sample_rate=1.0,
        profiles_sample_rate=1.0,
    )

# Create Flask app
app = Flask(__name__, template_folder='templates', static_folder='static')
secret_key = os.getenv('FLASK_SECRET_KEY')
if not secret_key:
    raise RuntimeError("CRITICAL: FLASK_SECRET_KEY environment variable is missing. Refusing to start.")
app.secret_key = secret_key

# Enable CSRF Protection
csrf = CSRFProtect(app)

# Session Security Configuration
app.config.update(
    SESSION_COOKIE_SECURE=os.getenv('FLASK_ENV') != 'development',
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=86400  # 24 hours
)

# CSRF Protection already initialized above
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

redis_url = os.getenv('REDIS_URL')
limiter_storage = redis_url if redis_url else "memory://"

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri=limiter_storage
)

# Import and register blueprints
from core.utils import retry_on_exception
from core.whatsapp_handler import whatsapp_bp

def get_authorized_report(report_id):
    """
    Fetch a report and ensure it belongs to the current user's company.
    Prevents IDOR (Insecure Direct Object Reference) vulnerabilities.
    """
    report = db.get_report(report_id)
    if not report:
        return None
        
    company = get_current_company()
    if not company or report.get('company_id') != company['id']:
        import logging
        logging.warning(f"IDOR ATTEMPT: User tried to access report {report_id} belonging to company {report.get('company_id')}")
        return None
        
    return report

from core.auth import auth_bp, login_required, get_current_user, get_current_company
from core.database import Database
from core.mailer import init_mail
from connectors.procore import ProcoreConnector
from connectors.base import ERPError

app.register_blueprint(whatsapp_bp)
csrf.exempt(whatsapp_bp) # Twilio cannot send CSRF tokens
# Explicitly exempt the view function to bypass Flask-WTF Blueprint bugs
if 'whatsapp.whatsapp_webhook' in app.view_functions:
    csrf.exempt(app.view_functions['whatsapp.whatsapp_webhook'])
app.register_blueprint(auth_bp)

# Initialize database
db = Database()

# Initialize mailer
mail = init_mail(app)

import threading
import time
import logging



from flask import g

@app.before_request
def check_trial_status():
    g.trial_days_left = None
    g.trial_expired = False
    g.subscription_plan = 'pro'
    g.subscription_status = None
    
    # 1. Skip static assets immediately for performance
    if request.endpoint and (request.endpoint == 'static' or request.endpoint == 'serve_media'):
        return

    # 2. If user is not logged in, nothing more to do
    if 'user_id' not in session:
        return
        
    # 3. User is logged in, fetch company info to populate g
    company = get_current_company()
    if not company:
        return
        
    g.subscription_plan = company.get('subscription_plan', 'pro')
    g.subscription_status = company.get('subscription_status', 'trialing')
    
    # 4. Check if we need to enforce trial expiration redirect
    skip_enforcement = ['auth.', 'health_check', 'landing', 'pricing', 'privacy', 'terms',
                      'super_admin_dashboard', 'extend_subscription', 'lemonsqueezy_webhook']
    
    if request.endpoint:
        for skip in skip_enforcement:
            if request.endpoint == skip or request.endpoint.startswith(skip):
                return
                
    # 5. Enforce trial logic
    if company.get('trial_ends_at'):
        try:
            trial_end_str = company['trial_ends_at']
            if isinstance(trial_end_str, datetime):
                trial_end = trial_end_str
            else:
                try:
                    trial_end = datetime.fromisoformat(trial_end_str)
                except ValueError:
                    trial_end = datetime.strptime(trial_end_str.split('.')[0], "%Y-%m-%d %H:%M:%S")
            
            # Remove timezone info for safe comparison
            if trial_end.tzinfo is not None:
                trial_end = trial_end.replace(tzinfo=None)
            
            now = datetime.utcnow()
            diff = trial_end - now
            
            if g.subscription_status == 'active':
                # Paid customer, no trial restrictions
                g.trial_days_left = None
                g.trial_expired = False
            elif g.subscription_status == 'trialing':
                if diff.total_seconds() > 0:
                    g.trial_days_left = diff.days
                else:
                    g.trial_expired = True
                    flash("Your 14-day free trial has expired. Please upgrade to continue using RapidSite AI.", "warning")
                    return redirect(url_for('pricing'))
        except Exception as e:
            print(f"Error parsing trial_ends_at: {e}")

# Serve media files
@app.route('/media/<path:filename>')
@login_required
def serve_media(filename):
    from flask import send_from_directory
    media_dir = os.path.join(os.path.dirname(__file__), 'data', 'media')
    return send_from_directory(media_dir, filename)

# Lazy init of Procore connector (token-based or OAuth)
def get_procore_connector(company_id: int = None):
    try:
        if company_id:
            # Load credentials from database
            db = Database()
            company = db.get_company(company_id)
            if company and company.get('procore_access_token'):
                return ProcoreConnector({
                    "access_token": company.get('procore_access_token'),
                    "refresh_token": company.get('procore_refresh_token'),
                    "company_id": company.get('procore_company_id'),
                    "client_id": os.getenv('PROCORE_CLIENT_ID'),
                    "client_secret": os.getenv('PROCORE_CLIENT_SECRET'),
                    "redirect_uri": os.getenv('PROCORE_REDIRECT_URI', request.host_url.rstrip('/') + '/procore/callback') if request else None
                })
            else:
                return None
        
        # Fallback to env vars only if no company_id provided (e.g. system background jobs)
        if os.getenv('PROCORE_ACCESS_TOKEN'):
            return ProcoreConnector()
        return None
    except Exception as e:
        print(f"❌ Procore connector init failed: {e}")
        return None


def sync_report_to_procore(report: dict):
    """Push approved report to Procore Daily Log."""
    # Get company ID from report
    company_id = report.get('company_id')
    
    # Project ID ALWAYS comes from company settings (Dashboard), not from report
    project_id = None
    
    if company_id:
        try:
            db = Database()
            company = db.get_company(company_id)
            if company:
                project_id = company.get('procore_default_project_id')
                print(f"✅ Project ID from Settings: {project_id}")
        except Exception as e:
            print(f"⚠️ Error fetching company for project ID: {e}")

    # Fallback to env var
    if not project_id:
        project_id = os.getenv('PROCORE_DEFAULT_PROJECT_ID')
        print(f"🧐 Project ID from Env: {project_id}")

    connector = get_procore_connector(company_id)
    if not connector:
        return False, "Procore connector unavailable"

    if not project_id:
        return False, "No project_id configured. Please set a Default Project in Settings."

    try:
        connector.authenticate()
        
        # PERSIST TOKENS: If auth refreshed them, we must save to DB
        if company_id:
            try:
                # Update tokens in DB to prevent 401 on next run
                # Using 2 hours (7200s) as default expiry since connector handles refresh internally
                expires_at = int(datetime.now().timestamp()) + 7200
                
                db = Database()
                db.update_company_procore_tokens(
                    company_id,
                    connector.access_token,
                    connector.refresh_token,
                    expires_at
                )
            except Exception as e:
                print(f"⚠️ Failed to persist Procore tokens: {e}")

        result = connector.push_daily_log(project_id, report['parsed_data'])
        erp_id = result.get("erp_id")
        db.mark_synced(report['id'], company_id=report['company_id'], erp_sync_id=erp_id)
        return True, erp_id
    except ERPError as e:
        print(f"❌ Procore sync failed for report {report.get('id')}: {e}")
        return False, str(e)
    except Exception as e:
        print(f"❌ Unexpected Procore error for report {report.get('id')}: {e}")
        return False, str(e)


# =============================================================================
# PROCORE OAUTH ROUTES
# =============================================================================

@app.route('/procore/auth')
@login_required
def procore_auth():
    """Initiate Procore OAuth flow."""
    try:
        # Prefer env var if set (essential for Render/HTTPS), else fallback to auto-detect
        redirect_uri = os.getenv('PROCORE_REDIRECT_URI') or url_for('procore_callback', _external=True)
        
        connector = ProcoreConnector({
            "client_id": os.getenv('PROCORE_CLIENT_ID'),
            "redirect_uri": redirect_uri
        })
        
        # Security: Prevent OAuth CSRF
        import secrets
        state = secrets.token_urlsafe(32)
        session['procore_oauth_state'] = state
        
        auth_url = connector.get_auth_url(state=state)
        return redirect(auth_url)
    except Exception as e:
        return f"Error initiating Procore auth: {e}", 500


@app.route('/procore/callback')
@login_required
def procore_callback():
    """Handle Procore OAuth callback."""
    code = request.args.get('code')
    error = request.args.get('error')
    state = request.args.get('state')
    
    if error:
        return f"Procore auth error: {error}", 400
    
    if not code:
        return "No code provided", 400
        
    # Security: Validate OAuth state
    expected_state = session.pop('procore_oauth_state', None)
    if not expected_state or state != expected_state:
        return "Invalid or missing state parameter. CSRF attempt detected.", 403
    
    try:
        # Must match the redirect_uri used in auth step
        redirect_uri = os.getenv('PROCORE_REDIRECT_URI') or url_for('procore_callback', _external=True)
        
        connector = ProcoreConnector({
             "client_id": os.getenv('PROCORE_CLIENT_ID'),
             "client_secret": os.getenv('PROCORE_CLIENT_SECRET'),
             "redirect_uri": redirect_uri
        })
        
        # Exchange code for tokens
        tokens = connector.exchange_code_for_token(code)
        
        # Get user's company
        company = get_current_company()
        if not company:
            return "No company associated with user", 400
        
        # Calculate expiration
        expires_in = tokens.get('expires_in', 7200)
        expires_at = int(datetime.now().timestamp()) + expires_in
        
        # Auto-fetch and store the first Procore company ID
        try:
            # We need to set the access token on the connector to use it immediately
            connector.access_token = tokens['access_token']
            companies = connector.get_companies()
            if companies and len(companies) > 0:
                db.update_company_procore_company_id(company['id'], str(companies[0]['id']))
        except Exception as fetch_err:
            print(f"⚠️ Could not auto-fetch Procore company ID: {fetch_err}")
        
        db.update_company_procore_tokens(
            company['id'],
            tokens['access_token'],
            tokens['refresh_token'],
            expires_at
        )
        
        flash("Successfully connected to Procore!", "success")
        return redirect(url_for('settings'))
        
    except Exception as e:
        print(f"❌ Procore callback failed: {e}")
        return f"Authentication failed: {str(e)}", 500


@app.route('/procore/disconnect', methods=['POST'])
@login_required
def procore_disconnect():
    """Disconnect Procore integration."""
    try:
        company = get_current_company()
        if not company:
            return "Unauthorized", 403
            
        # Update tokens with None to clear them (access, refresh, expiry)
        # Note: We keep the company_id and project_id for convenience on reconnect
        db.update_company_procore_tokens(
            company['id'],
            None,
            None,
            None
        )
        flash("Successfully disconnected from Procore", "info")
    except Exception as e:
        print(f"Disconnect failed: {e}")
        flash(f"Failed to disconnect: {e}", "error")
        
    return redirect(url_for('settings'))


@app.route('/settings/procore/project', methods=['POST'])
@login_required
def update_procore_project():
    """Update default Procore project."""
    company = get_current_company()
    if not company:
        return "Unauthorized", 403
        
    project_id = request.form.get('project_id')
    if project_id:
        db.update_company_procore_project(company['id'], project_id)

    flash("Procore settings updated successfully!", "success")
    return redirect(url_for('settings'))


# =============================================================================
# HEALTH CHECK
# =============================================================================

@app.route('/health')
@limiter.exempt
def health_check():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "service": "RapidSite AI",
        "version": "1.0.0"
    })


# =============================================================================
# SEO ROUTES
# =============================================================================

from flask import make_response

@app.route('/robots.txt')
def robots():
    content = "User-agent: *\nAllow: /\nDisallow: /dashboard\nDisallow: /settings\nSitemap: https://rapidsite.app/sitemap.xml\n"
    response = make_response(content)
    response.headers['Content-Type'] = 'text/plain'
    return response

@app.route('/sitemap.xml')
def sitemap():
    content = '''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url>
        <loc>https://rapidsite.app/</loc>
        <changefreq>weekly</changefreq>
        <priority>1.0</priority>
    </url>
    <url>
        <loc>https://rapidsite.app/pricing</loc>
        <changefreq>monthly</changefreq>
        <priority>0.8</priority>
    </url>
    <url>
        <loc>https://rapidsite.app/auth/login</loc>
        <changefreq>yearly</changefreq>
        <priority>0.5</priority>
    </url>
    <url>
        <loc>https://rapidsite.app/auth/register</loc>
        <changefreq>yearly</changefreq>
        <priority>0.5</priority>
    </url>
</urlset>'''
    response = make_response(content)
    response.headers['Content-Type'] = 'application/xml'
    return response

# =============================================================================
# DASHBOARD & MAIN ROUTES
# =============================================================================

@app.route('/')
def landing():
    """Main landing page."""
    # If user is already logged in, redirect to dashboard
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('landing.html')

@app.route('/pricing')
def pricing():
    """Pricing and plans page."""
    return render_template('pricing.html')

@app.route('/privacy')
def privacy():
    """Privacy policy page."""
    return render_template('privacy.html')

@app.route('/terms')
def terms():
    """Terms of service page."""
    return render_template('terms.html')


@app.route('/dashboard')
@login_required
def dashboard():
    """Main dashboard - shows pending reports for user's company."""
    company = get_current_company()
    user = get_current_user()
    
    page = request.args.get('page', 1, type=int)
    project_filter = request.args.get('project_id', None)
    per_page = 20
    offset = (page - 1) * per_page
    
    projects_list = []
    
    if company:
        raw_reports = db.get_reports_by_company(company['id'], project_id=project_filter, limit=per_page, offset=offset)
        stats = db.get_stats_by_company(company['id'])
        
        import json
        if company.get('procore_projects'):
            try:
                projects_list = json.loads(company['procore_projects'])
            except json.JSONDecodeError:
                pass
    else:
        # Fallback for users without company (shouldn't happen)
        raw_reports = db.get_reports(limit=per_page, offset=offset)
        stats = db.get_stats()
        
    reports_by_type = {
        'weather': [],
        'manpower': [],
        'notes': [],
        'timecards': [],
        'equipment': [],
        'visitors': [],
        'phone_calls': [],
        'inspections': [],
        'delivery': [],
        'safety': [],
        'accidents': [],
        'quantity': [],
        'productivity': [],
        'dumpster': [],
        'waste': [],
        'scheduled_work': [],
        'delays': [],
        'photos': []
    }
    
    for r in raw_reports:
        import json
        try:
            parsed = json.loads(r['parsed_data']) if isinstance(r['parsed_data'], str) else r['parsed_data']
        except:
            parsed = {}
            
        t = parsed.get('log_type', 'notes').lower()
        if t == 'materials': t = 'quantity'
        if t == 'production': t = 'productivity'
        
        # fallback for unexpected types
        if t not in reports_by_type:
            t = 'notes'
            
        reports_by_type[t].append(r)
        
    total_db_reports = stats.get('total', 0)
    total_pages = (total_db_reports + per_page - 1) // per_page
    
    return render_template('dashboard.html', 
                           reports_by_type=reports_by_type, 
                           total_reports=total_db_reports, 
                           stats=stats, 
                           user=user, 
                           company=company,
                           page=page,
                           total_pages=total_pages,
                           projects_list=projects_list,
                           project_filter=project_filter)


@app.route('/dashboard/export')
@login_required
def export_excel():
    company = get_current_company()
    if not company:
        return redirect(url_for('landing'))
        
    project_filter = request.args.get('project_id', None)
    
    # We want all reports for the export, maybe up to 10000
    raw_reports = db.get_reports_by_company(company['id'], project_id=project_filter, limit=10000, offset=0)
    
    import openpyxl
    from io import BytesIO
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Site Reports"
    
    # Headers matching the user's requested format
    headers = ['Date', 'Project', 'Log Type', 'Item / Crew / Subject', 'Qty / Hours', 'Status', 'Cost Code', 'Reported By', 'Original Source']
    ws.append(headers)
    
    for r in raw_reports:
        parsed = r.get('parsed_data', {})
        if isinstance(parsed, str):
            try:
                import json
                parsed = json.loads(parsed)
            except:
                parsed = {}
                
        date_str = str(r['created_at'])[:16]
        project_name = parsed.get('project_name') or 'N/A'
        log_type = (parsed.get('log_type') or 'N/A').title()
        item = parsed.get('item') or parsed.get('description') or 'N/A'
        
        quantity = ""
        if parsed.get('quantity'):
            quantity = f"{parsed.get('quantity')} {parsed.get('unit') or ''}"
        elif parsed.get('crew') and parsed.get('crew').get('hours'):
            quantity = f"{parsed.get('crew').get('hours')} hours"
        elif parsed.get('equipment_details') and parsed.get('equipment_details').get('hours_operating'):
            quantity = f"{parsed.get('equipment_details').get('hours_operating')} hours"
            
        status = r['status'].upper()
        cost_code = r.get('cost_code') or parsed.get('cost_code') or 'N/A'
        reported_by = r.get('reported_by') or 'N/A'
        raw_transcript = r.get('raw_transcript') or ''
        
        ws.append([date_str, project_name, log_type, item, quantity, status, cost_code, reported_by, raw_transcript])
        
    # Formatting widths
    for col in ws.columns:
        column_letter = col[0].column_letter
        ws.column_dimensions[column_letter].width = 20
    ws.column_dimensions['I'].width = 60 # Make the raw transcript column wider
        
    excel_file = BytesIO()
    wb.save(excel_file)
    excel_file.seek(0)
    
    filename = f"Site_Reports_{datetime.now().strftime('%Y%m%d')}.xlsx"
    from flask import send_file
    return send_file(excel_file, download_name=filename, as_attachment=True, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')



# =============================================================================
# ADMIN ROUTES
# =============================================================================

def is_super_admin():
    """Check if current user is super admin."""
    user = get_current_user()
    if not user:
        return False
        
    # Security: Use the database role, not a hardcoded email
    return user.get('role') == 'super_admin'

@app.route('/admin')
@login_required
def super_admin_dashboard():
    if not is_super_admin():
        flash("You do not have permission to access this page.", "error")
        return redirect(url_for('dashboard'))
        
    companies = db.get_all_companies()
    return render_template('admin.html', companies=companies, user=get_current_user())

@app.route('/admin/company/<int:company_id>/extend', methods=['POST'])
@csrf.exempt
@login_required
def extend_subscription(company_id):
    if not is_super_admin():
        return jsonify({"success": False, "error": "Unauthorized"}), 403
        
    data = request.get_json() or {}
    days = data.get('days', 14)
    status = data.get('status', 'active')
    
    success = db.extend_company_subscription(company_id, days=days, status=status)
    if success:
        return jsonify({"success": True, "message": f"Extended by {days} days."})
    return jsonify({"success": False, "error": "Company not found"}), 404


# =============================================================================
# API ROUTES
# =============================================================================

@app.route('/api/v1/latest_report_id')
@login_required
def latest_report_id():
    company = get_current_company()
    if not company:
        return jsonify({"latest_id": 0})
    
    reports = db.get_reports_by_company(company['id'], limit=1)
    latest_id = reports[0]['id'] if reports else 0
    return jsonify({"latest_id": latest_id})

@app.route('/api/v1/reports', methods=['GET'])
@login_required
def api_list_reports():
    """List reports with optional filtering."""
    status = request.args.get('status')
    project_id = request.args.get('project_id')
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)
    
    reports = db.get_reports(
        status=status,
        project_id=project_id,
        limit=limit,
        offset=offset
    )
    
    return jsonify({
        "success": True,
        "count": len(reports),
        "reports": reports
    })


@app.route('/api/v1/reports', methods=['POST'])
@login_required
def api_create_report():
    """Create a new report (for direct API access)."""
    from core.brain import ConstructionBrain
    
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "No JSON data"}), 400
    
    transcript = data.get('transcript')
    if not transcript:
        return jsonify({"success": False, "error": "transcript is required"}), 400
    
    try:
        brain = ConstructionBrain()
        parsed_data = brain.parse_text(transcript)
        
        report_id = db.create_report(
            raw_transcript=transcript,
            parsed_data=parsed_data,
            project_id=data.get('project_id'),
            reported_by=data.get('reported_by')
        )
        
        return jsonify({
            "success": True,
            "report_id": report_id,
            "parsed_data": parsed_data,
            "message": "Report created successfully"
        }), 201
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/v1/reports/<int:report_id>', methods=['GET'])
@login_required
def api_get_report(report_id):
    """Get a single report."""
    report = get_authorized_report(report_id)
    if not report:
        return jsonify({"success": False, "error": "Report not found"}), 404
    
    return jsonify({"success": True, "report": report})


@app.route('/api/v1/reports/<int:report_id>/approve', methods=['POST'])
@login_required
def api_approve_report(report_id):
    """Approve a pending report."""
    data = request.get_json() or {}
    approved_by = data.get('approved_by', 'API User')
    
    company_id = get_current_company()['id']
    success = db.approve_report(report_id, company_id, approved_by)
    
    if success:
        return jsonify({"success": True, "message": "Report approved"})
    else:
        return jsonify({"success": False, "error": "Report not found or already processed"}), 400


@app.route('/api/v1/reports/<int:report_id>/reject', methods=['POST'])
@login_required
def api_reject_report(report_id):
    """Reject a pending report."""
    data = request.get_json() or {}
    reason = data.get('reason')
    
    company_id = get_current_company()['id']
    success = db.reject_report(report_id, company_id, reason)
    
    if success:
        return jsonify({"success": True, "message": "Report rejected"})
    else:
        return jsonify({"success": False, "error": "Report not found or already processed"}), 400


@app.route('/api/v1/reports/<int:report_id>/sync', methods=['POST'])
@login_required
def api_sync_report(report_id):
    """Sync report to ERP (placeholder for Procore integration)."""
    report = get_authorized_report(report_id)
    if not report:
        return jsonify({"success": False, "error": "Report not found"}), 404
    
    if report['status'] != 'approved':
        return jsonify({"success": False, "error": "Report must be approved first"}), 400
    
    success, erp_id_or_error = sync_report_to_procore(report)
    if success:
        return jsonify({
            "success": True,
            "message": "Report synced to Procore",
            "erp_sync_id": erp_id_or_error
        })
    else:
        return jsonify({"success": False, "error": erp_id_or_error}), 502


@app.route('/api/v1/stats', methods=['GET'])
@login_required
def api_stats():
    """Get report statistics."""
    stats = db.get_stats()
    return jsonify({"success": True, "stats": stats})


@app.route('/api/v1/notifications', methods=['GET'])
@login_required
def api_notifications():
    """Get notification data for real-time updates."""
    company = get_current_company()
    
    if not company:
        return jsonify({"success": False, "error": "No company"}), 400
    
    # Get pending reports count
    stats = db.get_stats_by_company(company['id'])
    pending_count = stats.get('pending', 0)
    
    # Get latest pending reports (for toast notifications)
    reports = db.get_reports_by_company(company['id'], status='pending', limit=5)
    
    # Convert to serializable format
    latest_reports = []
    for r in reports:
        latest_reports.append({
            'id': r['id'],
            'raw_transcript': r['raw_transcript'][:100] if r.get('raw_transcript') else '',
            'reported_by': r.get('reported_by', 'Unknown'),
            'created_at': str(r.get('created_at', ''))
        })
    
    return jsonify({
        "success": True,
        "pending_count": pending_count,
        "latest_reports": latest_reports
    })


# =============================================================================
# WHATSAPP NOTIFICATION
# =============================================================================

def send_whatsapp_notification(phone_number: str, message: str):
    """Send WhatsApp notification to foreman about report status."""
    try:
        from twilio.rest import Client
        
        account_sid = os.getenv('TWILIO_ACCOUNT_SID')
        auth_token = os.getenv('TWILIO_AUTH_TOKEN')
        from_number = os.getenv('TWILIO_WHATSAPP_NUMBER', '+14155238886')
        
        if not account_sid or not auth_token:
            print(f"⚠️ Twilio credentials not set, skipping notification")
            return False
        
        client = Client(account_sid, auth_token)
        
        # Format numbers for WhatsApp
        if not phone_number.startswith('whatsapp:'):
            phone_number = f"whatsapp:{phone_number}"
        if not from_number.startswith('whatsapp:'):
            from_number = f"whatsapp:{from_number}"
        
        client.messages.create(
            body=message,
            from_=from_number,
            to=phone_number
        )
        print(f"✅ WhatsApp notification sent to {phone_number}")
        return True
    except Exception as e:
        print(f"❌ Failed to send WhatsApp notification: {e}")
        return False


# =============================================================================
# DASHBOARD ACTION ROUTES
# =============================================================================

@app.route('/dashboard/approve/<int:report_id>', methods=['POST'])
@login_required
def dashboard_approve(report_id):
    """Approve report from dashboard and notify foreman."""
    report = get_authorized_report(report_id)
    company_id = get_current_company()['id']
    db.approve_report(report_id, company_id, approved_by="Dashboard User")
    
    # Attempt Procore sync (best-effort; errors are logged)
    if report:
        success, erp_id_or_error = sync_report_to_procore({**report, "id": report_id})
        if not success:
            print(f"⚠️ Procore sync failed for report {report_id}: {erp_id_or_error}")
            try:
                flash(f"Approved, but failed to sync to Procore: {erp_id_or_error}", "warning")
            except Exception:
                pass # Flash might fail if no secret key set properly, though we have one
        else:
            try:
                flash(f"Report approved and synced to Procore (ID: {erp_id_or_error})", "success")
            except Exception:
                pass

    # Send WhatsApp notification
    if report and report.get('reported_by'):
        parsed = report.get('parsed_data', {})
        item = parsed.get('item', 'Report')
        quantity = parsed.get('quantity')
        unit = parsed.get('unit', '')
        log_type = parsed.get('log_type', 'notes').title()
        
        # Build quantity line only if there's actual data
        qty_line = ""
        if quantity:
            qty_line = f"\n📊 {quantity} {unit}".rstrip() if unit else f"\n📊 {quantity}"
        
        message = f"""✅ Report #{report_id} APPROVED!

📋 {item}{qty_line}
📂 Category: {log_type}

👷 Logged to system by supervisor."""
        
        send_whatsapp_notification(report['reported_by'], message)
    
    return redirect(url_for('dashboard'))


@app.route('/dashboard/edit/<int:report_id>', methods=['POST'])
@login_required
def dashboard_edit(report_id):
    """Edit the parsed data of a report before approval."""
    try:
        new_data = request.json
        if not new_data:
            return jsonify({"success": False, "error": "No data provided"}), 400
            
        company_id = get_current_company()['id']
        success = db.update_report_parsed_data(report_id, company_id, new_data)
        if success:
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Report not found or update failed"}), 404
            
    except Exception as e:
        print(f"Error updating report {report_id}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/dashboard/reject/<int:report_id>', methods=['POST'])
@login_required
def dashboard_reject(report_id):
    """Reject report from dashboard and notify foreman."""
    report = get_authorized_report(report_id)
    company_id = get_current_company()['id']
    db.reject_report(report_id, company_id)
    
    # Send WhatsApp notification
    if report and report.get('reported_by'):
        parsed = report.get('parsed_data', {})
        item = parsed.get('item', 'Report')
        
        message = f"""❌ Report #{report_id} REJECTED

📋 {item}

⚠️ Please verify and resend if needed."""
        
        send_whatsapp_notification(report['reported_by'], message)
    
    return redirect(url_for('dashboard'))


@app.route('/dashboard/sync/<int:report_id>', methods=['POST'])
@login_required
def dashboard_sync(report_id):
    """Manually trigger Procore sync for an approved report."""
    report = get_authorized_report(report_id)
    if not report:
        flash("Report not found", "error")
        return redirect(url_for('dashboard'))
        
    success, erp_id_or_error = sync_report_to_procore(report)
    
    if success:
        flash(f"✅ Sync successful! Procore ID: {erp_id_or_error}", "success")
    else:
        if "No project_id" in erp_id_or_error:
             flash("Sync failed: No Default Project configured. Please go to Settings and select a project.", "warning")
        else:
             flash(f"❌ Sync failed: {erp_id_or_error}", "error")
             
    return redirect(url_for('dashboard'))


@app.route('/settings')
@login_required
def settings():
    """Settings page."""
    user = get_current_user()
    company = get_current_company()
    users = db.get_users_by_company(company['id']) if company else []
    
    # Get authorized numbers with names
    authorized_numbers = db.get_authorized_numbers(company['id']) if company else []
    
    # Get Procore projects if connected
    procore_projects = []
    procore_companies = []
    
    try:
        connector = get_procore_connector(company['id'])
        # Fetch projects (connector handles auth)
        if connector:
            procore_projects = connector.get_projects()
    except Exception as e:
        print(f"Failed to fetch Procore data: {e}")

    return render_template('settings.html', user=user, company=company, users=users, authorized_numbers=authorized_numbers, procore_projects=procore_projects)


@app.route('/settings/sync_master_data', methods=['POST'])
@login_required
def sync_master_data():
    """Fetch Master Data (Vendors, Cost Codes, Locations) from Procore and save to DB."""
    company = get_current_company()
    if not company:
        flash("No company associated with account.", "error")
        return redirect(url_for('settings'))
        
    connector = get_procore_connector(company['id'])
    if not connector:
        flash("Please connect to Procore first before syncing master data.", "error")
        return redirect(url_for('settings'))
        
    project_id = company.get('procore_default_project_id')
    if not project_id:
        flash("Please set a Default Project first.", "warning")
        return redirect(url_for('settings'))
        
    try:
        vendors = connector.get_vendors(project_id)
        cost_codes = connector.get_cost_codes(project_id)
        locations = connector.get_locations(project_id)
        projects = connector.get_projects() # Defaults to current company_id in connector
        
        # We only need minimal info to feed the LLM
        v_list = [{"id": v.get("id"), "name": v.get("name")} for v in vendors if v.get("name")]
        cc_list = [{"id": c.get("id"), "full_code": c.get("full_code"), "name": c.get("name")} for c in cost_codes if c.get("full_code")]
        loc_list = [{"id": l.get("id"), "name": l.get("name")} for l in locations if l.get("name")]
        proj_list = [{"id": p.get("id"), "name": p.get("name")} for p in projects if p.get("name")]
        
        import json
        db.update_company_procore_lists(
            company['id'],
            json.dumps(v_list, ensure_ascii=False),
            json.dumps(cc_list, ensure_ascii=False),
            json.dumps(loc_list, ensure_ascii=False)
        )
        db.update_company_procore_projects(company['id'], json.dumps(proj_list, ensure_ascii=False))
        flash(f"✅ Successfully synced {len(proj_list)} projects, {len(v_list)} vendors, {len(cc_list)} cost codes, and {len(loc_list)} locations.", "success")
    except Exception as e:
        flash(f"❌ Failed to sync master data: {e}", "error")
        
    return redirect(url_for('settings'))


@app.route('/settings/update', methods=['POST'])
@login_required
def update_settings():
    """Update settings (Legacy)."""
    user = get_current_user()
    if user['role'] != 'admin':
        flash("Unauthorized. Only admins can update settings.", "error")
        return redirect(url_for('settings'))
    
    # This route is now mostly for company name updates if we enabled them
    return redirect(url_for('settings'))


@app.route('/settings/numbers/add', methods=['POST'])
@login_required
def add_authorized_number():
    """Add a new authorized WhatsApp number."""
    user = get_current_user()
    if user['role'] != 'admin':
        flash("Unauthorized. Only admins can add authorized numbers.", "error")
        return redirect(url_for('settings'))
    
    name = request.form.get('employee_name')
    number = request.form.get('phone_number')
    job_title = request.form.get('job_title')
    
    if name and number:
        db.add_authorized_number(user['company_id'], number, name, job_title)
    
    return redirect(url_for('settings'))

@app.route('/settings/team/add', methods=['POST'])
@login_required
def add_team_member():
    """Add a new team member (dashboard user)."""
    user = get_current_user()
    if user['role'] != 'admin':
        flash("Unauthorized. Only admins can add team members.", "error")
        return redirect(url_for('settings'))
        
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip().lower()
    job_title = request.form.get('job_title', '').strip()
    role = request.form.get('role', 'supervisor')
    
    # Security: Prevent privilege escalation (Mass Assignment)
    if role not in ['supervisor', 'admin']:
        role = 'supervisor'
        
    password = request.form.get('password', '')
    
    if not name or not email or not password:
        flash("Name, Email, and Password are required for a team member.", "error")
        return redirect(url_for('settings'))
        
    if db.get_user_by_email(email):
        flash("A user with this email already exists.", "error")
        return redirect(url_for('settings'))
        
    try:
        from core.auth import hash_password
        db.create_user(
            email=email,
            password_hash=hash_password(password),
            name=name,
            company_id=user['company_id'],
            role=role,
            job_title=job_title
        )
        flash(f"Team member {name} added successfully!", "success")
    except Exception as e:
        flash(f"Failed to add team member: {str(e)}", "error")
        
    return redirect(url_for('settings'))


@app.route('/settings/numbers/delete/<int:number_id>', methods=['POST'])
@login_required
def delete_authorized_number(number_id):
    """Delete an authorized WhatsApp number."""
    user = get_current_user()
    if user['role'] != 'admin':
        flash("Unauthorized. Only admins can delete authorized numbers.", "error")
        return redirect(url_for('settings'))
    
    db.remove_authorized_number(number_id, user['company_id'])
    
    return redirect(url_for('settings'))

@app.route('/webhook/lemonsqueezy', methods=['POST'])
@csrf.exempt
def lemonsqueezy_webhook():
    """Handle LemonSqueezy subscription events."""
    secret = os.getenv('LEMON_SQUEEZY_WEBHOOK_SECRET', '')
    if not secret:
        return "No secret configured", 500

    raw_body = request.get_data()
    signature = request.headers.get('X-Signature', '')

    # Verify signature
    digest = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(digest, signature):
        return "Invalid signature", 401

    try:
        data = request.json
        event_name = data.get('meta', {}).get('event_name')
        custom_data = data.get('meta', {}).get('custom_data', {})
        
        company_id = custom_data.get('company_id')
        if not company_id:
            # Fallback to email matching if company_id wasn't passed in checkout
            user_email = data.get('data', {}).get('attributes', {}).get('user_email')
            if user_email:
                user = db.get_user_by_email(user_email)
                if user:
                    company_id = user['company_id']

        if not company_id:
            return "Company ID not found", 404

        if event_name in ['subscription_created', 'subscription_updated']:
            # Extend by 32 days (1 month + grace) and set active
            db.extend_company_subscription(int(company_id), 32, 'active')
        elif event_name in ['subscription_cancelled', 'subscription_expired']:
            # Terminate subscription
            db.extend_company_subscription(int(company_id), 0, 'cancelled')

        return "OK", 200
    except Exception as e:
        print(f"Webhook Error: {e}")
        return "Internal Server Error", 500



# =============================================================================
# MAIN
# =============================================================================

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_ENV') == 'development'
    
    print("=" * 60)
    print("🏗️  RapidSite AI - Construction Report System")
    print("=" * 60)
    print(f"🌐 Dashboard: http://localhost:{port}")
    print(f"📡 WhatsApp Webhook: http://localhost:{port}/webhook/whatsapp")
    print(f"🔧 API Base: http://localhost:{port}/api/v1")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=port, debug=debug)
