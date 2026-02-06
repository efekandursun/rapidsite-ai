"""
FieldFlow AI - Main Flask Application
REST API + Dashboard for construction report management.
"""

import os
from flask import Flask, jsonify, request, render_template, redirect, url_for, session
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

app.register_blueprint(whatsapp_bp)
app.register_blueprint(auth_bp)

# Initialize database
db = Database()

# Initialize mailer
mail = init_mail(app)


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
    
    # TODO: Implement actual Procore sync
    # For now, just mark as synced
    db.mark_synced(report_id, erp_sync_id="MOCK-SYNC-ID")
    
    return jsonify({
        "success": True,
        "message": "Report synced to ERP",
        "erp_sync_id": "MOCK-SYNC-ID"
    })


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
    
    # Send WhatsApp notification
    if report and report.get('reported_by'):
        parsed = report.get('parsed_data', {})
        item = parsed.get('item', 'Report')
        quantity = parsed.get('quantity', '')
        unit = parsed.get('unit', '')
        
        message = f"""✅ Report #{report_id} APPROVED!

📋 {item}
📊 {quantity} {unit}

👷 Logged to system by supervisor."""
        
        send_whatsapp_notification(report['reported_by'], message)
    
    return redirect(url_for('dashboard'))


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


@app.route('/settings')
@login_required
def settings():
    """Settings page."""
    user = get_current_user()
    company = get_current_company()
    users = db.get_users_by_company(company['id']) if company else []
    
    # Get authorized numbers with names
    authorized_numbers = db.get_authorized_numbers(company['id']) if company else []
    
    return render_template('settings.html', user=user, company=company, users=users, authorized_numbers=authorized_numbers)


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
