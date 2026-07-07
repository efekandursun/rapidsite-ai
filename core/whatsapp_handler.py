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
    
    try:
        # Process with brain
        result = brain.process_audio(audio_path)
        
        # Find company
        company = db.get_company_by_whatsapp(from_number)
        company_id = company['id'] if company else None
        
        if not company_id:
            return {'error': 'Unknown number', 'transcript': result['transcript']}
        
        # Save to database
        parsed_items = result['parsed_data']
        if not isinstance(parsed_items, list):
            parsed_items = [parsed_items]
            
        report_ids = []
        for item in parsed_items:
            rid = db.create_report(
                raw_transcript=result['transcript'],
                parsed_data=item,
                project_id=project_id,
                reported_by=from_number,
                company_id=company_id
            )
            report_ids.append(rid)
        
        result['report_ids'] = report_ids
        result['parsed_data_list'] = parsed_items
        result['company_name'] = company['name']
        return result
        
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

    # Parse with brain
    parsed_data = brain.parse_text(text)
    if not isinstance(parsed_data, list):
        parsed_data = [parsed_data]
    
    # Save to database
    report_ids = []
    for item in parsed_data:
        rid = db.create_report(
            raw_transcript=text,
            parsed_data=item,
            project_id=project_id,
            reported_by=from_number,
            company_id=company_id
        )
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
        
    msg = f"✅ *{len(parsed_list)} Report(s) Received!*\n\n"
    
    for i, parsed in enumerate(parsed_list):
        r_id = report_ids[i] if i < len(report_ids) else 'N/A'
        msg += f"📋 *ID:* #{r_id} | *Type:* {parsed.get('log_type', 'N/A').title()}\n"
        
        if parsed.get('item'):
            msg += f"🔧 *Item:* {parsed.get('item')}\n"
        
        if parsed.get('quantity'):
            unit = parsed.get('unit', '')
            msg += f"📊 *Quantity:* {parsed.get('quantity')} {unit}\n"
        
        if parsed.get('cost_code'):
            msg += f"💰 *Cost Code:* {parsed.get('cost_code')}\n"
            
        msg += "\n"
    
    msg += "⏳ _Pending supervisor approval_"
    
    return msg
