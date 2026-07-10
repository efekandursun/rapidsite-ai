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
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from flask import Blueprint, request, abort, Response
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client as TwilioClient
from twilio.request_validator import RequestValidator

from core.brain import ConstructionBrain, TranscriptionError, ParsingError
from core.database import Database

# Create Blueprint
whatsapp_bp = Blueprint('whatsapp', __name__)

# Initialize components
brain = ConstructionBrain()
db = Database()

# Lightweight worker pool for async processing. For production, replace with a
# proper queue (RQ/Celery) but this keeps webhook latency low immediately.
executor = ThreadPoolExecutor(max_workers=4)

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

# In-memory idempotency cache for Twilio MessageSid (best-effort; replace with
# persistent store for multi-instance setups).
processed_sids = {}
sid_lock = threading.Lock()


def _purge_old_sids(ttl_seconds: int = 3600):
    """Drop idempotency entries older than ttl to bound memory."""
    cutoff = time.time() - ttl_seconds
    to_delete = [sid for sid, ts in processed_sids.items() if ts < cutoff]
    for sid in to_delete:
        processed_sids.pop(sid, None)


@whatsapp_bp.route('/webhook/whatsapp', methods=['POST'])
def whatsapp_webhook():
    """Twilio WhatsApp webhook handler (fast return + background work)."""

    # Validate signature if token is configured
    if request_validator:
        signature = request.headers.get('X-Twilio-Signature', '')
        url = request.url
        # Proxy fix for Render/Heroku (they terminate SSL so request.url is http://)
        if request.headers.get('X-Forwarded-Proto') == 'https':
            url = url.replace('http://', 'https://', 1)
            
        params = request.form.to_dict()  # Twilio signs form params
        if not request_validator.validate(url, params, signature):
            abort(403)

    message_sid = request.values.get('MessageSid')
    if not message_sid:
        abort(400)

    # Idempotency check (best-effort in-memory)
    with sid_lock:
        _purge_old_sids()
        if message_sid in processed_sids:
            # Already handled; acknowledge to Twilio
            resp = MessagingResponse()
            resp.message("✅ Already received. Processing underway.")
            return Response(str(resp), mimetype='application/xml')
        processed_sids[message_sid] = time.time()

    from_number = request.values.get('From', '')
    message_body = request.values.get('Body', '')
    num_media = int(request.values.get('NumMedia', 0))

    # Quick ACK to Twilio; heavy lifting offloaded
    ack = MessagingResponse()
    ack.message("✅ Received. Processing now...")

    # Kick background processing
    executor.submit(handle_message_async, message_sid, from_number, message_body, num_media, request.values)

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
                message_body = "Ekli fotoğraf/video gönderildi."

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
        msg = twilio_client.messages.create(body=body, from_=from_number, to=to_number)
        print(f"✅ Twilio message sent: SID={msg.sid}")
    except Exception as e:
        print(f"❌ Failed to send WhatsApp follow-up: {e}")
        logging.exception("Failed to send WhatsApp follow-up")


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
        reporter_str = f"{emp_name} - {job_title}"
    elif emp_name:
        reporter_str = emp_name
    else:
        reporter_str = from_number
    
    # Check if there is an incomplete report for this user
    incomplete_report = db.get_incomplete_report_for_user(reporter_str) or db.get_incomplete_report_for_user(from_number)
    
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
                
            if updated_event:
                combined_transcript = incomplete_report['raw_transcript'] + f"\n[EK BİLGİ]: {text}"
                final_transcript = combined_transcript
                
                new_status = updated_event.get('status', 'pending')
                if new_status == 'complete':
                    new_status = 'pending'
                    
                media_json = json.dumps(media_paths) if media_paths else None
                
                db.update_incomplete_report(
                    incomplete_report['id'], 
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
                rid = db.create_report(
                    raw_transcript=text,
                    parsed_data=item,
                    project_id=project_id,
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
            
            media_json = json.dumps(media_paths) if media_paths else None
            rid = db.create_report(
                raw_transcript=text,
                parsed_data=item,
                project_id=project_id,
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
    Returns relative path if permanent, absolute temp path otherwise.
    """
    # Get Twilio auth for media download
    auth = None
    if os.getenv("TWILIO_ACCOUNT_SID"):
        auth = (os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
    
    response = requests.get(url, auth=auth)
    response.raise_for_status()
    
    if permanent:
        import uuid
        filename = f"{uuid.uuid4().hex}{suffix}"
        media_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "media")
        os.makedirs(media_dir, exist_ok=True)
        filepath = os.path.join(media_dir, filename)
        with open(filepath, "wb") as f:
            f.write(response.content)
        # return relative path from static
        return f"media/{filename}"
    else:
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
    Format confirmation message for user.
    """
    parsed_list = result.get('parsed_data_list', [])
    report_ids = result.get('report_ids', [])
    
    if not parsed_list:
        return "⚠️ Mesajınız alındı ama işlenemedi."
        
    completed_msgs = []
    incomplete_msgs = []
    
    for i, parsed in enumerate(parsed_list):
        r_id = report_ids[i] if i < len(report_ids) else 'N/A'
        
        if parsed.get('status') == 'incomplete' and parsed.get('follow_up_question'):
            incomplete_msgs.append(f"❓ *EKSİK BİLGİ:* {parsed.get('follow_up_question')}")
        else:
            msg = f"📋 *ID:* #{r_id} | *Type:* {parsed.get('log_type', 'N/A').title()}\n"
            if parsed.get('item'):
                msg += f"🔧 *Item:* {parsed.get('item')}\n"
            if parsed.get('quantity'):
                unit = parsed.get('unit', '')
                msg += f"📊 *Quantity:* {parsed.get('quantity')} {unit}\n"
            if parsed.get('cost_code'):
                msg += f"💰 *Cost Code:* {parsed.get('cost_code')}\n"
            completed_msgs.append(msg)
            
    final_response = ""
    if completed_msgs:
        final_response += f"✅ *{len(completed_msgs)} Rapor Alındı!*\n" + "\n".join(completed_msgs) + "\n"
        
    if incomplete_msgs:
        if final_response:
            final_response += "\n---\n\n"
        final_response += "\n\n".join(incomplete_msgs)
        
    if not incomplete_msgs and completed_msgs:
        final_response += "\n⏳ _Onay bekliyor_"
        
    return final_response
