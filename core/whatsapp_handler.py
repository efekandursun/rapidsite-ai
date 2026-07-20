"""
RapidSite AI - WhatsApp Handler
Twilio webhook handler for WhatsApp voice/text messages.

Improvements in this version:
- Twilio signature validation for incoming webhooks (fails closed on mismatch).
- Idempotency using Twilio MessageSid to avoid duplicate processing.
- Async processing: webhook returns fast, heavy work runs in background thread.
- Proactive WhatsApp responses after background processing completes.
"""

import os
import json
import tempfile
import requests
import logging
from flask import Blueprint, request, abort, Response
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client as TwilioClient
from twilio.request_validator import RequestValidator

from core.brain import ConstructionBrain, TranscriptionError, ParsingError
from core.database import Database
from core.storage import upload_media_to_storage

# Create Blueprint
whatsapp_bp = Blueprint('whatsapp', __name__)

# Initialize components
brain = ConstructionBrain()
db = Database()

# Twilio client (optional, for sending proactive messages)
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
twilio_client = None
if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
    twilio_client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
else:
    logging.warning("Twilio credentials not fully set; outbound WhatsApp replies disabled.")

# Twilio signature validator (fail closed when token present)
request_validator = RequestValidator(TWILIO_AUTH_TOKEN) if TWILIO_AUTH_TOKEN else None


@whatsapp_bp.route('/webhook/whatsapp', methods=['POST'])
def whatsapp_webhook():
    """Twilio WhatsApp webhook handler (fast return + DB Queue)."""

    if not TWILIO_AUTH_TOKEN:
        logging.error("CRITICAL SECURITY: TWILIO_AUTH_TOKEN is missing. Rejecting webhook request to prevent spoofing.")
        abort(403)
        
    # Validate signature if token is configured
    if request_validator:
        signature = request.headers.get('X-Twilio-Signature', '')
        url = request.url
        # Proxy fix for Render/Heroku (they terminate SSL so request.url is http://)
        if request.headers.get('X-Forwarded-Proto') == 'https':
            url = url.replace('http://', 'https://', 1)
            
        params = request.form.to_dict()  # Twilio signs form params
        if not request_validator.validate(url, params, signature):
            logging.warning(f"⚠️ Invalid Twilio Signature! URL: {url} | Params: {params}")
            abort(403)

    message_sid = request.values.get('MessageSid')
    if not message_sid:
        abort(400)

    # Detach data from Flask request context
    form_data = dict(request.values)

    # Push to Database Queue to prevent duplicates
    created = db.create_webhook_job(message_sid, form_data)

    if not created:
        # Duplicate message
        resp = MessagingResponse()
        resp.message("✅ Already received. Processing underway.")
        return Response(str(resp), mimetype='application/xml')

    # Offload heavy work to Redis Queue (RQ) or fallback to threading
    try:
        import os
        from redis import Redis
        from rq import Queue
        
        redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
        redis_conn = Redis.from_url(redis_url)
        q = Queue('rapidsite-tasks', connection=redis_conn)
        
        q.enqueue(
            handle_message_async, 
            message_sid, 
            form_data.get('From', ''), 
            form_data.get('Body', ''), 
            int(form_data.get('NumMedia', 0)), 
            form_data
        )
    except Exception as e:
        # Fallback to threading if Redis is not available locally
        logging.error(f"❌ Redis queue failed, using threading fallback. Error: {e}")
        import threading
        t = threading.Thread(target=handle_message_async, args=(
            message_sid, 
            form_data.get('From', ''), 
            form_data.get('Body', ''), 
            int(form_data.get('NumMedia', 0)), 
            form_data
        ))
        t.start()

    # Quick ACK to Twilio; heavy lifting offloaded to background worker
    ack = MessagingResponse()
    ack.message("✅ Received. Processing now...")
    return Response(str(ack), mimetype='application/xml')


def handle_message_async(message_sid: str, from_number: str, message_body: str, num_media: int, values):
    """Process message in background thread and send a follow-up reply."""
    try:
        project_id = extract_project_id(message_body) or None
        response = MessagingResponse()

        audio_url = None
        media_paths = []
        
        # Process all media
        if num_media > 0:
            for i in range(num_media):
                url = values.get(f'MediaUrl{i}', '')
                mtype = values.get(f'MediaContentType{i}', '')
                
                if 'audio' in mtype or 'ogg' in mtype:
                    audio_url = url
                elif 'image' in mtype or 'video' in mtype:
                    ext = ".jpg" if 'image' in mtype else ".mp4"
                    path = download_media(url, suffix=ext, permanent=True)
                    media_paths.append(path)

        if audio_url:
            # Voice message (with optional attachments)
            result = process_voice_message(audio_url, project_id, from_number, media_paths)
        else:
            # Text message (with optional attachments)
            if not message_body.strip() and not media_paths:
                response.message("👋 Welcome to RapidSite AI! Send a voice note or text report.")
                return send_followup(from_number, str(response))

            if message_body.lower().startswith('register '):
                response.message("🛠 Registration flow coming soon. Please ask your supervisor to add your number for now.")
                return send_followup(from_number, str(response))
                
            if not message_body.strip() and media_paths:
                message_body = "Attached photo/video received."

            result = process_text_message(message_body, project_id, from_number, media_paths)

        if result.get('company_name'):
            confirm_msg = format_confirmation(result)
            response.message(confirm_msg)
        else:
            response.message("⚠️ Your number is not registered to any company. Please contact your supervisor to add your number to the system.")

        send_followup(from_number, str(response))

    except TranscriptionError as e:
        send_followup(from_number, f"❌ Could not transcribe audio: {str(e)}")
    except ParsingError as e:
        send_followup(from_number, f"❌ Could not parse message: {str(e)}")
    except Exception as e:
        logging.exception("WhatsApp processing failed")
        send_followup(from_number, f"❌ Error: {str(e)}")


def send_followup(to_number: str, response_xml: str):
    """Send a WhatsApp message using Twilio with the prepared TwiML payload."""
    if not twilio_client:
        logging.warning("Twilio client not configured; cannot send follow-up.")
        return

    # Twilio expects plain text body, not full TwiML, for proactive outbound
    # messages. We extract <Body> content when possible.
    body = extract_body_from_twiml(response_xml)
    if not body:
        # Fallback if it's just a raw string
        body = response_xml if "<" not in response_xml else "✅ Processed."

    # Ensure WhatsApp prefix
    if not to_number.startswith('whatsapp:'):
        to_number = f"whatsapp:{to_number}"

    from_number = os.getenv('TWILIO_WHATSAPP_NUMBER', '+14155238886')
    if not from_number.startswith('whatsapp:'):
        from_number = f"whatsapp:{from_number}"

    try:
        print(f"📤 Sending WhatsApp follow-up to {to_number}")
        print(f"📝 Body preview: {body[:200]}")
        
        # Check if this is a Report Ready message, if so, we'll send the text and then a button
        is_ready_msg = "*REPORT READY*" in body
        
        # Send the main text message
        if is_ready_msg:
            # We don't want the button text in the body if we are sending a button
            clean_body = body.split("*ACTIONS:*")[0].strip() if "*ACTIONS:*" in body else body
            msg = twilio_client.messages.create(body=clean_body, from_=from_number, to=to_number)
            print(f"✅ Twilio text message sent: SID={msg.sid}")
            
            # Now send the button message
            button_sid = _get_or_create_button_sid()
            if button_sid:
                btn_msg = twilio_client.messages.create(
                    content_sid=button_sid,
                    from_=from_number,
                    to=to_number
                )
                print(f"✅ Twilio button sent: SID={btn_msg.sid}")
        else:
            msg = twilio_client.messages.create(body=body, from_=from_number, to=to_number)
            print(f"✅ Twilio message sent: SID={msg.sid}")
            
    except Exception as e:
        print(f"❌ Failed to send WhatsApp follow-up: {e}")
        logging.exception("Failed to send WhatsApp follow-up")

# Cache for button template SID
_BUTTON_CONTENT_SID = None

def _get_or_create_button_sid():
    """Create a Twilio Content API template for the approval/edit buttons if it doesn't exist."""
    global _BUTTON_CONTENT_SID
    if _BUTTON_CONTENT_SID:
        return _BUTTON_CONTENT_SID
        
    try:
        account_sid = os.getenv('TWILIO_ACCOUNT_SID')
        auth_token = os.getenv('TWILIO_AUTH_TOKEN')
        url = "https://content.twilio.com/v1/Content"
        payload = {
            "friendly_name": "Fieldflow Action Buttons",
            "language": "en",
            "types": {
                "twilio/quick-reply": {
                    "body": "What would you like to do?",
                    "actions": [
                        {"title": "👍 Send", "id": "send"},
                        {"title": "✏️ Edit", "id": "edit"}
                    ]
                }
            }
        }
        res = requests.post(url, auth=(account_sid, auth_token), json=payload, timeout=5)
        if res.status_code == 201:
            _BUTTON_CONTENT_SID = res.json().get('sid')
            return _BUTTON_CONTENT_SID
    except Exception as e:
        logging.error(f"Failed to create button content: {e}")
    return None


def extract_body_from_twiml(twiml_xml: str) -> str:
    """Best-effort extraction of message body from MessagingResponse XML."""
    import re
    # Twilio TwiML format: <Response><Message><Body>text</Body></Message></Response>
    match = re.search(r'<Body>(.*?)</Body>', twiml_xml, re.DOTALL)
    if match:
        return match.group(1).strip()
    # Fallback: try <Message> directly (older format)
    match = re.search(r'<Message>(.*?)</Message>', twiml_xml, re.DOTALL)
    if match:
        body = match.group(1).strip()
        # Remove any nested tags
        body = re.sub(r'<[^>]+>', '', body).strip()
        return body if body else None
    return None


def process_voice_message(audio_url: str, project_id: str, from_number: str, media_paths: list = None) -> dict:
    """Process voice message through AI Brain."""
    if media_paths is None: media_paths = []
    
    # 1. Download audio temp file
    audio_path = download_media(audio_url, suffix=".ogg", permanent=False)
    
    db = Database()
    
    # Get company from sender's number
    company = db.get_company_by_whatsapp(from_number)
    company_id = company['id'] if company else None
    
    if not company_id:
        return {'error': 'Unknown number'}
        
    try:
        # 1. Transcribe audio
        new_transcript = brain.transcribe_audio(audio_path)
        
        # 2. Process with memory (append to incomplete report if exists)
        return _process_text_with_memory(new_transcript, project_id, from_number, company, media_paths)
        
    finally:
        # Cleanup temp file
        if os.path.exists(audio_path):
            os.unlink(audio_path)


def process_text_message(text: str, project_id: str, from_number: str, media_paths: list = None) -> dict:
    """Process text message through AI Brain."""
    if media_paths is None: media_paths = []
    db = Database()
    
    # Get company context
    company = db.get_company_by_whatsapp(from_number)
    company_id = company['id'] if company else None
    
    if not company_id:
        return {'error': 'Unknown number', 'transcript': text}

    return _process_text_with_memory(text, project_id, from_number, company, media_paths)

def _process_text_with_memory(text: str, project_id: str, from_number: str, company: dict, media_paths: list) -> dict:
    company_id = company['id']
    
    emp_name = company.get('employee_name')
    job_title = company.get('job_title')
    if emp_name and job_title:
        reporter_str = f"{emp_name} - {job_title} ({from_number})"
    elif emp_name:
        reporter_str = f"{emp_name} ({from_number})"
    else:
        reporter_str = from_number
    
    # Check if there is an incomplete report for this user
    incomplete_report = db.get_incomplete_report_for_user(reporter_str) or db.get_incomplete_report_for_user(from_number)
    
    # --- NEW APPROVAL LOGIC ---
    cleaned_text = text.strip().lower()
    # Remove any accidental quotation marks if the user copy-pasted the example
    cleaned_text = cleaned_text.replace('"', '').replace("'", "").replace("“", "").replace("”", "").replace("‘", "").replace("’", "").strip()
    
    # --- INTERACTIVE BUTTON HANDLERS ---
    is_approve = cleaned_text in ['👍 send', 'send', '👍 dashboard\'a gönder', '1', '1.', '1)', 'onayla', 'approve', 'yes', 'y', 'bir', 'one']
    is_edit_btn = cleaned_text in ['✏️ edit', 'edit', '✏️ düzenle', 'düzenle']
    
    all_pending = db.get_all_pending_reports_for_user(reporter_str) or db.get_all_pending_reports_for_user(from_number)
    
    # If user clicked Edit button
    if is_edit_btn and all_pending:
        # Filter to only unlocked reports
        import json
        unlocked_reports = []
        for r in all_pending:
            try: p = json.loads(r['parsed_data'])
            except: p = {}
            if not p.get('locked'): unlocked_reports.append(r)
                
        if len(unlocked_reports) == 1:
            rep = unlocked_reports[0]
            with db.get_connection() as conn:
                db._execute(conn, "UPDATE site_reports SET status='incomplete' WHERE id=?", (rep['id'],))
            return {'company_name': company['name'], 'direct_reply': f"✏️ Report #{rep['id']} is in Edit mode. What would you like to change or add?"}
        elif len(unlocked_reports) > 1:
            return {'company_name': company['name'], 'direct_reply': "Please reply with the *ID number* of the report you want to edit. (e.g. 8, 9, or 10)"}
        else:
            return {'company_name': company['name'], 'direct_reply': "[LOCKED] Your recent reports have already been sent to the Dashboard and cannot be edited."}

    # Matches: Pure number when multiple reports exist
    import re
    is_standalone_number = re.match(r'^(\d+)$', cleaned_text)
    
    if is_standalone_number and all_pending:
        report_id = int(is_standalone_number.group(1))
        # Find if this ID is in unlocked reports
        import json
        target_report = None
        for r in all_pending:
            if r['id'] == report_id:
                try: p = json.loads(r['parsed_data'])
                except: p = {}
                if not p.get('locked'): target_report = r
                break
        
        if target_report:
            with db.get_connection() as conn:
                db._execute(conn, "UPDATE site_reports SET status='incomplete' WHERE id=?", (target_report['id'],))
            return {'company_name': company['name'], 'direct_reply': f"✏️ Report #{report_id} is in Edit mode. What would you like to change or add?"}
    
    # --- SPECIFIC REPORT EDIT COMMAND ---
    # Matches: "edit 9: change quantity to 5" or "edit #9 change quantity"
    edit_match = re.match(r'^(?:edit|düzenle|duzenle|değiştir|degistir)\s*(?:rapor|report|numara|#)?\s*(\d+)[:\s,\-]+(.*)', cleaned_text)
    if not edit_match:
        # Try reverse WITH explicit keyword: "9 numarayı düzenle..."
        edit_match = re.match(r'^(\d+)\s*(?:numarayı|numarali|numaralı|raporu|report|i|ı)?\s*(?:edit|düzenle|duzenle|değiştir|degistir)[:\s,\-]+(.*)', cleaned_text)
    if not edit_match:
        # Try reverse WITHOUT explicit keyword but WITH strong suffix reference: "9 un companyisi..."
        # Suffixes like un, in, ü, u, numaralı, raporu strongly imply referencing the ID
        edit_match = re.match(r'^(\d+)\s*(?:numarayı|numarali|numaralı|raporu|report|\'ü|\'u|\'un|\'in|\'nun|\'nin|un|in|nun|nin|ü|u|yi|yı|inci|ıncı)\s+([^:]+)', cleaned_text)
        
    if edit_match:
        report_id = int(edit_match.group(1))
        correction_text = edit_match.group(2).strip()
        if not correction_text:
            return {'company_name': company['name'], 'direct_reply': "Please provide the correction. (e.g. 'Edit 9: change the quantity to 5')"}
        
        # We need to fetch the specific report by ID
        specific_report = db._execute(db.get_connection(), "SELECT * FROM site_reports WHERE id=?", (report_id,)).fetchone()
        if specific_report:
            specific_report = db._row_to_dict(specific_report)
            if str(specific_report['reported_by']) in [reporter_str, from_number]:
                try:
                    import json
                    parsed = json.loads(specific_report['parsed_data'])
                except:
                    parsed = {}
                
                if parsed.get('locked'):
                    return {'company_name': company['name'], 'direct_reply': f"[LOCKED] Report #{report_id} has already been sent to the Dashboard and cannot be edited."}
                
                incomplete_report = specific_report
                text = correction_text
                is_approve = False
                cleaned_text = text.strip().lower()
            else:
                return {'company_name': company['name'], 'direct_reply': f"[ERROR] Report #{report_id} not found or you don't have permission to edit it."}
        else:
            return {'company_name': company['name'], 'direct_reply': f"[ERROR] Report #{report_id} not found."}
    else:
        is_reject = cleaned_text in ['2', '2.', '2)', 'reddet', 'hayır', 'hayir', 'reject', 'no', 'n', 'iki', 'two']

    if is_approve or is_reject:
        if all_pending:
            import json
            # Filter to only unlocked reports
            unlocked_reports = []
            for r in all_pending:
                try:
                    p = json.loads(r['parsed_data'])
                except:
                    p = {}
                if not p.get('locked'):
                    unlocked_reports.append((r, p))
                    
            if not unlocked_reports:
                return {'company_name': company['name'], 'direct_reply': "[LOCKED] Your recent reports have already been sent to the Dashboard and cannot be edited. Please send a new message for a new report."}

            if is_approve:
                for rep, parsed in unlocked_reports:
                    parsed['locked'] = True
                    db.update_report_parsed_data(rep['id'], company['id'], parsed)
                
                count = len(unlocked_reports)
                return {'company_name': company['name'], 'direct_reply': f"✅ {count} report(s) successfully sent to the Dashboard."}
            
            elif is_reject:
                if len(unlocked_reports) == 1:
                    rep, parsed = unlocked_reports[0]
                    with db.get_connection() as conn:
                        db._execute(conn, "UPDATE site_reports SET status='incomplete' WHERE id=?", (rep['id'],))
                    return {'company_name': company['name'], 'direct_reply': f"✏️ Report #{rep['id']} is in Edit mode. What would you like to change or add?"}
                else:
                    return {'company_name': company['name'], 'direct_reply': "Please reply with the *ID number* of the report you want to edit. (e.g. 8, 9, or 10)"}
        # end of all_pending logic

    
    parsed_data_list = []
    report_ids = []
    final_transcript = text
    
    # Flag to determine if we should fallback to normal parsing
    use_normal_parsing = True
    
    if incomplete_report:
        try:
            resolution = brain.resolve_incomplete(incomplete_report['parsed_data'], text, company)
            updated_event = resolution.get('updated_incomplete_event')
            new_events = resolution.get('new_events', [])
            
            if updated_event or new_events:
                use_normal_parsing = False
            else:
                use_normal_parsing = False
                # The AI couldn't link it and didn't find new events. Do not fall back to normal parsing to prevent garbage.
                q = incomplete_report['parsed_data'].get('follow_up_question', 'Please provide the missing information.')
                return {
                    'company_name': company['name'],
                    'direct_reply': f"❓ *I didn't quite get that.*\nI couldn't fully understand your message or audio. Could you please answer this question again:\n\n{q}"
                }
                
            if updated_event:
                combined_transcript = incomplete_report['raw_transcript'] + f"\n[ADDITIONAL INFO]: {text}"
                final_transcript = combined_transcript
                
                new_status = updated_event.get('status', 'pending')
                if new_status == 'complete':
                    new_status = 'pending'
                    
                media_json = json.dumps(media_paths) if media_paths else None
                
                db.update_incomplete_report(
                    incomplete_report['id'], 
                    company['id'],
                    combined_transcript, 
                    updated_event, 
                    new_status,
                    media_json
                )
                report_ids.append(incomplete_report['id'])
                parsed_data_list.append(updated_event)
                
            for item in new_events:
                s = item.get('status', 'pending')
                if s == 'complete': s = 'pending'
                
                media_json = json.dumps(media_paths) if media_paths else None
                
                detected_project_id = item.get('project_id') or project_id
                
                rid = db.create_report(
                    raw_transcript=text,
                    parsed_data=item,
                    project_id=detected_project_id,
                    reported_by=reporter_str,
                    company_id=company_id,
                    media_paths=media_json
                )
                if s == 'incomplete':
                    with db.get_connection() as conn:
                        db._execute(conn, "UPDATE site_reports SET status='incomplete' WHERE id=?", (rid,))
                report_ids.append(rid)
                parsed_data_list.append(item)
                
        except Exception as e:
            logging.error(f"Error resolving incomplete report: {e}")
            use_normal_parsing = True

    if use_normal_parsing:
        parsed_data = brain.parse_text(text, company=company)
        if not isinstance(parsed_data, list):
            parsed_data = [parsed_data]
            
        for item in parsed_data:
            s = item.get('status', 'pending')
            if s == 'complete': s = 'pending'
            
            # Use AI-detected project_id or fallback to the provided default project_id
            detected_project_id = item.get('project_id') or project_id
            
            media_json = json.dumps(media_paths) if media_paths else None
            rid = db.create_report(
                raw_transcript=text,
                parsed_data=item,
                project_id=detected_project_id,
                reported_by=reporter_str,
                company_id=company_id,
                media_paths=media_json
            )
            if s == 'incomplete':
                with db.get_connection() as conn:
                    db._execute(conn, "UPDATE site_reports SET status='incomplete' WHERE id=?", (rid,))
            report_ids.append(rid)
            parsed_data_list.append(item)
            
    return {
        'transcript': final_transcript,
        'parsed_data_list': parsed_data_list,
        'report_ids': report_ids,
        'company_name': company['name']
    }

def download_media(url: str, suffix: str = ".ogg", permanent: bool = False) -> str:
    """
    Download media file from Twilio to temp file or permanent storage.
    Returns URL path if permanent, absolute temp path otherwise.
    """
    if permanent:
        return upload_media_to_storage(url, suffix)
        
    # Get Twilio auth for temporary media download
    auth = None
    if os.getenv("TWILIO_ACCOUNT_SID"):
        auth = (os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
    
    response = requests.get(url, auth=auth)
    response.raise_for_status()
    
    # Save to temp file
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(response.content)
        return f.name


def extract_project_id(text: str) -> str:
    """
    Extract project ID from message text.
    Looks for patterns like PRJ-001, PROJECT-123, etc.
    """
    import re
    match = re.search(r'(PRJ|PROJECT|PROJ)[-_]?(\d+)', text.upper())
    if match:
        return f"PRJ-{match.group(2)}"
    return None


def format_confirmation(result: dict) -> str:
    """
    Format confirmation message for user based on Procore fields.
    """
    if 'direct_reply' in result:
        return result['direct_reply']

    parsed_list = result.get('parsed_data_list', [])
    report_ids = result.get('report_ids', [])
    
    if not parsed_list:
        return "[WARNING] Message received but could not be processed."
        
    completed_msgs = []
    incomplete_msgs = []
    
    for i, parsed in enumerate(parsed_list):
        r_id = report_ids[i] if i < len(report_ids) else 'N/A'
        
        if parsed.get('status') == 'incomplete' and parsed.get('follow_up_question'):
            incomplete_msgs.append(f"[MISSING INFO] {parsed.get('follow_up_question')}")
        else:
            log_type = parsed.get('log_type', 'unknown').lower()
            msg = f"[ID: #{r_id} | TYPE: {log_type.upper()}]\n"
            
            def val(v): return str(v) if v not in (None, "", "null") else "Boş (Empty)"
            
            loc = parsed.get('location', {})
            loc_name = loc.get('name') if isinstance(loc, dict) else loc
            
            if log_type == "delivery":
                details = parsed.get('delivery_details', {})
                q = parsed.get('quantity', '')
                u = parsed.get('unit', '')
                item = parsed.get('item', '')
                contents = f"{q} {u} {item}".strip()
                
                msg += f"- Time: {val(details.get('time'))}\n"
                msg += f"- Delivery From: {val(details.get('delivery_from'))}\n"
                msg += f"- Tracking Number: {val(details.get('tracking_number'))}\n"
                msg += f"- Contents: {val(contents)}\n"
                msg += f"- Comments: {val(parsed.get('description'))}\n"
                
            elif log_type == "equipment":
                details = parsed.get('equipment_details', {})
                msg += f"- Equipment Name: {val(parsed.get('item'))}\n"
                msg += f"- Hours Operating: {val(details.get('hours_operating') or parsed.get('quantity'))}\n"
                msg += f"- Hours Idle: {val(details.get('hours_idle'))}\n"
                msg += f"- Inspected: {'Yes' if details.get('inspected') else 'No'}\n"
                msg += f"- Cost Code: {val(parsed.get('cost_code'))}\n"
                msg += f"- Location: {val(loc_name)}\n"
                msg += f"- Notes/Comments: {val(parsed.get('description'))}\n"
                
            elif log_type == "manpower":
                crew = parsed.get('crew', {})
                msg += f"- Company/Sub: {val(crew.get('company_name'))}\n"
                msg += f"- Workers: {val(crew.get('count') or parsed.get('quantity'))}\n"
                msg += f"- Hours: {val(crew.get('hours'))}\n"
                msg += f"- Trade: {val(crew.get('trade') or parsed.get('item'))}\n"
                msg += f"- Location: {val(loc_name)}\n"
                msg += f"- Comments: {val(parsed.get('description'))}\n"
                
            elif log_type in ("materials", "production", "quantity"):
                msg += f"- Item: {val(parsed.get('item'))}\n"
                msg += f"- Quantity: {val(parsed.get('quantity'))} {val(parsed.get('unit'))}\n"
                msg += f"- Cost Code: {val(parsed.get('cost_code'))}\n"
                msg += f"- Location: {val(loc_name)}\n"
                msg += f"- Comments: {val(parsed.get('description'))}\n"
                
            else:
                msg += f"- Item: {val(parsed.get('item'))}\n"
                msg += f"- Quantity: {val(parsed.get('quantity'))} {val(parsed.get('unit'))}\n"
                msg += f"- Location: {val(loc_name)}\n"
                msg += f"- Cost Code: {val(parsed.get('cost_code'))}\n"
                msg += f"- Comments: {val(parsed.get('description'))}\n"
                
            completed_msgs.append(msg)
            
    final_msg = ""
    if completed_msgs:
        final_msg += "*REPORT READY*\n\n" + "\n\n".join(completed_msgs)
        # Note: ACTIONS text is now handled by the interactive button logic in send_followup
        
    if incomplete_msgs:
        if final_msg: final_msg += "\n\n"
        final_msg += "\n".join(incomplete_msgs)
        
    return final_msg
