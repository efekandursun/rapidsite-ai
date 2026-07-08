"""
FieldFlow AI - WhatsApp Handler
Twilio webhook handler for WhatsApp voice/text messages.

Improvements in this version:
- Twilio signature validation for incoming webhooks (fails closed on mismatch).
- Idempotency using Twilio MessageSid to avoid duplicate processing.
- Async processing: webhook returns fast, heavy work runs in background thread.
- Proactive WhatsApp responses after background processing completes.
"""

import os
import tempfile
import requests
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from flask import Blueprint, request, abort
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
            return str(resp)
        processed_sids[message_sid] = time.time()

    from_number = request.values.get('From', '')
    message_body = request.values.get('Body', '')
    num_media = int(request.values.get('NumMedia', 0))

    # Quick ACK to Twilio; heavy lifting offloaded
    ack = MessagingResponse()
    ack.message("✅ Received. Processing now...")

    # Kick background processing
    executor.submit(handle_message_async, message_sid, from_number, message_body, num_media, request.values)

    return str(ack)


def handle_message_async(message_sid: str, from_number: str, message_body: str, num_media: int, values):
    """Process message in background thread and send a follow-up reply."""
    try:
        project_id = extract_project_id(message_body) or None
        response = MessagingResponse()

        if num_media > 0:
            media_url = values.get('MediaUrl0', '')
            media_type = values.get('MediaContentType0', '')
            if 'audio' in media_type or 'ogg' in media_type:
                result = process_voice_message(media_url, project_id, from_number)
            else:
                response.message("⚠️ Please send a voice message or text. Images are not supported yet.")
                return send_followup(from_number, str(response))
        else:
            if not message_body.strip():
                response.message("👋 Welcome to FieldFlow AI! Send a voice note or text report.")
                return send_followup(from_number, str(response))

            if message_body.lower().startswith('register '):
                response.message("🛠 Registration flow coming soon. Please ask your supervisor to add your number for now.")
                return send_followup(from_number, str(response))

            result = process_text_message(message_body, project_id, from_number)

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
        body = "✅ Processed."

    # Ensure WhatsApp prefix
    if not to_number.startswith('whatsapp:'):
        to_number = f"whatsapp:{to_number}"

    from_number = os.getenv('TWILIO_WHATSAPP_NUMBER', '+14155238886')
    if not from_number.startswith('whatsapp:'):
        from_number = f"whatsapp:{from_number}"

    try:
        twilio_client.messages.create(body=body, from_=from_number, to=to_number)
    except Exception:
        logging.exception("Failed to send WhatsApp follow-up")


def extract_body_from_twiml(twiml_xml: str) -> str:
    """Best-effort extraction of message body from MessagingResponse XML."""
    import re
    match = re.search(r"<Message>(.*?)</Message>", twiml_xml, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


def process_voice_message(media_url: str, project_id: str, from_number: str) -> dict:
    """
    Process voice message: Download → Transcribe → Parse → Save.
    """
    # Download audio file
    audio_path = download_media(media_url)
    
    # Find company early for Procore Master Data matching
    company = db.get_company_by_whatsapp(from_number)
    company_id = company['id'] if company else None
    
    if not company_id:
        # Without company, we can't save anyway
        return {'error': 'Unknown number'}
        
    try:
        # 1. Transcribe audio
        new_transcript = brain.transcribe_audio(audio_path)
        
        # 2. Process with memory (append to incomplete report if exists)
        return _process_text_with_memory(new_transcript, project_id, from_number, company)
        
    finally:
        # Cleanup temp file
        if os.path.exists(audio_path):
            os.unlink(audio_path)


def process_text_message(text: str, project_id: str, from_number: str) -> dict:
    """
    Process text message: Parse → Save.
    """
    # Find company
    company = db.get_company_by_whatsapp(from_number)
    company_id = company['id'] if company else None
    
    if not company_id:
        return {'error': 'Unknown number', 'transcript': text}

    return _process_text_with_memory(text, project_id, from_number, company)

def _process_text_with_memory(text: str, project_id: str, from_number: str, company: dict) -> dict:
    company_id = company['id']
    
    # Check if there is an incomplete report for this user
    incomplete_report = db.get_incomplete_report_for_user(from_number)
    
    if incomplete_report:
        # Append new text to old transcript
        combined_transcript = incomplete_report['raw_transcript'] + f"\n[EK BİLGİ]: {text}"
        
        # Parse combined text
        parsed_data = brain.parse_text(combined_transcript, company=company)
        if not isinstance(parsed_data, list):
            parsed_data = [parsed_data]
            
        # Update the incomplete report with the FIRST item (assuming it completes the flow)
        # If there are multiple items now, we update the first and create new for rest
        first_item = parsed_data[0]
        new_status = first_item.get('status', 'pending')
        if new_status == 'complete':
            new_status = 'pending' # Ready for approval
            
        db.update_incomplete_report(
            incomplete_report['id'], 
            combined_transcript, 
            first_item, 
            new_status
        )
        
        report_ids = [incomplete_report['id']]
        
        # If LLM extracted more events from combined text, save them as new
        for item in parsed_data[1:]:
            s = item.get('status', 'pending')
            if s == 'complete': s = 'pending'
            rid = db.create_report(
                raw_transcript=combined_transcript,
                parsed_data=item,
                project_id=project_id,
                reported_by=from_number,
                company_id=company_id
            )
            # manually set status (create_report defaults to pending, we might need an update_status here if we want it to be incomplete, 
            # but for simplicity let's assume the follow up completes the main issue)
            if s == 'incomplete':
                db._execute(db.get_connection(), "UPDATE site_reports SET status='incomplete' WHERE id=?", (rid,))
            report_ids.append(rid)
            
        return {
            'transcript': combined_transcript,
            'parsed_data_list': parsed_data,
            'report_ids': report_ids,
            'company_name': company['name']
        }
    else:
        # Normal flow: brand new message
        parsed_data = brain.parse_text(text, company=company)
        if not isinstance(parsed_data, list):
            parsed_data = [parsed_data]
        
        report_ids = []
        for item in parsed_data:
            status = item.get('status', 'pending')
            if status == 'complete': status = 'pending'
            
            rid = db.create_report(
                raw_transcript=text,
                parsed_data=item,
                project_id=project_id,
                reported_by=from_number,
                company_id=company_id
            )
            
            # Since create_report hardcodes 'pending' or we can't pass status yet without schema changes,
            # we'll run a quick update if it's incomplete
            if status == 'incomplete':
                with db.get_connection() as conn:
                    db._execute(conn, "UPDATE site_reports SET status='incomplete' WHERE id=?", (rid,))
                    conn.commit()
            
            report_ids.append(rid)
        
        return {
            'transcript': text,
            'parsed_data_list': parsed_data,
            'report_ids': report_ids,
            'company_name': company['name']
        }

def download_media(url: str) -> str:
    """
    Download media file from Twilio to temp file.
    """
    # Get Twilio auth for media download
    auth = None
    if os.getenv("TWILIO_ACCOUNT_SID"):
        auth = (os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
    
    response = requests.get(url, auth=auth)
    response.raise_for_status()
    
    # Save to temp file
    suffix = ".ogg"  # WhatsApp voice messages are OGG format
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
