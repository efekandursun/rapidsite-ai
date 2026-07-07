import os
from datetime import datetime
from flask import Flask, jsonify, request, render_template, redirect, url_for, session, flash
from dotenv import load_dotenv

load_dotenv()

# Create Flask app
app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')

# Import and register blueprints
from core.whatsapp_handler import whatsapp_bp
from core.auth import auth_bp, login_required, get_current_user, get_current_company
from core.database import Database
from core.mailer import init_mail
from connectors.procore import ProcoreConnector
from connectors.base import ERPError

app.register_blueprint(whatsapp_bp)
app.register_blueprint(auth_bp)

# Initialize database
db = Database()

# Initialize mailer
mail = init_mail(app)

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
        
        # Fallback to env vars (legacy/single-tenant)
        return ProcoreConnector()
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
        db.mark_synced(report['id'], erp_sync_id=erp_id)
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
        auth_url = connector.get_auth_url()
        return redirect(auth_url)
    except Exception as e:
        return f"Error initiating Procore auth: {e}", 500


@app.route('/procore/callback')
@login_required
def procore_callback():
    """Handle Procore OAuth callback."""
    code = request.args.get('code')
    error = request.args.get('error')
    
    if error:
        return f"Procore auth error: {error}", 400
    
    if not code:
        return "No code provided", 400
    
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
        
        # Get Procore company ID (optional, can be selected later)
        # For now we'll just store the tokens
        
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
    procore_company_id = request.form.get('procore_company_id')
    
    if project_id:
        db.update_company_procore_project(company['id'], project_id)
        
    if procore_company_id:
        db.update_company_procore_company_id(company['id'], procore_company_id)

    flash("Procore settings updated successfully!", "success")
    return redirect(url_for('settings'))


# =============================================================================
# HEALTH CHECK
# =============================================================================

@app.route('/health')
def health_check():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "service": "FieldFlow AI",
        "version": "1.0.0"
    })


# =============================================================================
# DASHBOARD ROUTES
# =============================================================================

@app.route('/')
@login_required
def dashboard():
    """Main dashboard - shows pending reports for user's company."""
    company = get_current_company()
    user = get_current_user()
    
    if company:
        reports = db.get_reports_by_company(company['id'], limit=50)
        stats = db.get_stats_by_company(company['id'])
    else:
        # Fallback for users without company (shouldn't happen)
        reports = db.get_reports(limit=50)
        stats = db.get_stats()
    
    return render_template('dashboard.html', reports=reports, stats=stats, user=user, company=company)


@app.route('/reports/<int:report_id>')
def view_report(report_id):
    """View single report details."""
    report = db.get_report(report_id)
    if not report:
        return "Report not found", 404
    return render_template('report_detail.html', report=report)


# =============================================================================
# API ROUTES
# =============================================================================

@app.route('/api/v1/reports', methods=['GET'])
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
def api_get_report(report_id):
    """Get a single report."""
    report = db.get_report(report_id)
    if not report:
        return jsonify({"success": False, "error": "Report not found"}), 404
    
    return jsonify({"success": True, "report": report})


@app.route('/api/v1/reports/<int:report_id>/approve', methods=['POST'])
def api_approve_report(report_id):
    """Approve a pending report."""
    data = request.get_json() or {}
    approved_by = data.get('approved_by', 'API User')
    
    success = db.approve_report(report_id, approved_by)
    
    if success:
        return jsonify({"success": True, "message": "Report approved"})
    else:
        return jsonify({"success": False, "error": "Report not found or already processed"}), 400


@app.route('/api/v1/reports/<int:report_id>/reject', methods=['POST'])
def api_reject_report(report_id):
    """Reject a pending report."""
    data = request.get_json() or {}
    reason = data.get('reason')
    
    success = db.reject_report(report_id, reason)
    
    if success:
        return jsonify({"success": True, "message": "Report rejected"})
    else:
        return jsonify({"success": False, "error": "Report not found or already processed"}), 400


@app.route('/api/v1/reports/<int:report_id>/sync', methods=['POST'])
def api_sync_report(report_id):
    """Sync report to ERP (placeholder for Procore integration)."""
    report = db.get_report(report_id)
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
def dashboard_approve(report_id):
    """Approve report from dashboard and notify foreman."""
    report = db.get_report(report_id)
    db.approve_report(report_id, approved_by="Dashboard User")
    
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
            
        success = db.update_report_parsed_data(report_id, new_data)
        if success:
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Report not found or update failed"}), 404
            
    except Exception as e:
        print(f"Error updating report {report_id}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/dashboard/reject/<int:report_id>', methods=['POST'])
def dashboard_reject(report_id):
    """Reject report from dashboard and notify foreman."""
    report = db.get_report(report_id)
    db.reject_report(report_id)
    
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
    report = db.get_report(report_id)
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


@app.route('/settings/update', methods=['POST'])
@login_required
def update_settings():
    """Update settings (Legacy)."""
    user = get_current_user()
    if user['role'] != 'admin':
        return "Unauthorized", 403
    
    # This route is now mostly for company name updates if we enabled them
    return redirect(url_for('settings'))


@app.route('/settings/numbers/add', methods=['POST'])
@login_required
def add_authorized_number():
    """Add a new authorized WhatsApp number."""
    user = get_current_user()
    if user['role'] != 'admin':
        return "Unauthorized", 403
    
    name = request.form.get('employee_name')
    number = request.form.get('phone_number')
    
    if name and number:
        db.add_authorized_number(user['company_id'], number, name)
    
    return redirect(url_for('settings'))


@app.route('/settings/numbers/delete/<int:number_id>', methods=['POST'])
@login_required
def delete_authorized_number(number_id):
    """Delete an authorized WhatsApp number."""
    user = get_current_user()
    if user['role'] != 'admin':
        return "Unauthorized", 403
    
    db.remove_authorized_number(number_id, user['company_id'])
    
    return redirect(url_for('settings'))


# =============================================================================
# MAIN
# =============================================================================

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_ENV') == 'development'
    
    print("=" * 60)
    print("🏗️  FieldFlow AI - Construction Report System")
    print("=" * 60)
    print(f"🌐 Dashboard: http://localhost:{port}")
    print(f"📡 WhatsApp Webhook: http://localhost:{port}/webhook/whatsapp")
    print(f"🔧 API Base: http://localhost:{port}/api/v1")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=port, debug=debug)
