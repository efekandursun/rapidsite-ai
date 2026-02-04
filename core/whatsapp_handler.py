"""
FieldFlow AI - WhatsApp Handler
Twilio webhook handler for WhatsApp voice/text messages.
"""

import os
import tempfile
import requests
from flask import Blueprint, request
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client as TwilioClient

from core.brain import ConstructionBrain, TranscriptionError, ParsingError
from core.database import Database

# Create Blueprint
whatsapp_bp = Blueprint('whatsapp', __name__)

# Initialize components
brain = ConstructionBrain()
db = Database()

# Twilio client (optional, for sending proactive messages)
twilio_client = None
if os.getenv("TWILIO_ACCOUNT_SID"):
    twilio_client = TwilioClient(
        os.getenv("TWILIO_ACCOUNT_SID"),
        os.getenv("TWILIO_AUTH_TOKEN")
    )


@whatsapp_bp.route('/webhook/whatsapp', methods=['POST'])
def whatsapp_webhook():
    """
    Twilio WhatsApp webhook handler.
    
    Receives voice/text messages, processes with AI, saves to database.
    """
    # Get message details
    from_number = request.values.get('From', '')
    message_body = request.values.get('Body', '')
    num_media = int(request.values.get('NumMedia', 0))
    
    # Extract project ID from message or use default
    project_id = extract_project_id(message_body) or "DEFAULT"
    
    response = MessagingResponse()
    
    try:
        if num_media > 0:
            # Handle voice message
            media_url = request.values.get('MediaUrl0', '')
            media_type = request.values.get('MediaContentType0', '')
            
            if 'audio' in media_type or 'ogg' in media_type:
                result = process_voice_message(media_url, project_id, from_number)
            else:
                response.message("⚠️ Please send a voice message or text. Images are not supported yet.")
                return str(response)
        else:
            # Handle text message
            if not message_body.strip():
                response.message("👋 Welcome to FieldFlow AI! Send a voice note or text report.")
                return str(response)
            
            # Check if this is a registration message
            if message_body.lower().startswith('register '):
                # TODO: Implement registration flow
                pass
            
            result = process_text_message(message_body, project_id, from_number)
        
        # Add company info to result if available
        if result.get('company_name'):
            confirm_msg = format_confirmation(result)
            response.message(confirm_msg)
        else:
            # Unknown number
            response.message("⚠️ Your number is not registered to any company. Please contact your supervisor to add your number to the system.")
        
    except TranscriptionError as e:
        response.message(f"❌ Could not transcribe audio: {str(e)}")
    except ParsingError as e:
        response.message(f"❌ Could not parse message: {str(e)}")
    except Exception as e:
        response.message(f"❌ Error: {str(e)}")
    
    return str(response)


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
        report_id = db.create_report(
            raw_transcript=result['transcript'],
            parsed_data=result['parsed_data'],
            project_id=project_id,
            reported_by=from_number,
            company_id=company_id
        )
        
        result['report_id'] = report_id
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
    
    # Save to database
    report_id = db.create_report(
        raw_transcript=text,
        parsed_data=parsed_data,
        project_id=project_id,
        reported_by=from_number,
        company_id=company_id
    )
    
    return {
        'transcript': text,
        'parsed_data': parsed_data,
        'report_id': report_id,
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
    parsed = result.get('parsed_data', {})
    
    msg = "✅ *Report Received!*\n\n"
    msg += f"📋 *ID:* #{result.get('report_id', 'N/A')}\n"
    msg += f"📁 *Type:* {parsed.get('log_type', 'N/A').title()}\n"
    
    if parsed.get('item'):
        msg += f"🔧 *Item:* {parsed.get('item')}\n"
    
    if parsed.get('quantity'):
        unit = parsed.get('unit', '')
        msg += f"📊 *Quantity:* {parsed.get('quantity')} {unit}\n"
    
    if parsed.get('cost_code'):
        msg += f"💰 *Cost Code:* {parsed.get('cost_code')}\n"
    
    msg += "\n⏳ _Pending supervisor approval_"
    
    return msg
