"""
RapidSite AI - Storage Module
Handles media uploads to Supabase Storage.
"""

import os
import uuid
import tempfile
import requests
import logging
from dotenv import load_dotenv

load_dotenv()

# Initialize Supabase client
supabase_client = None
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if SUPABASE_URL and SUPABASE_KEY and SUPABASE_URL != "your_supabase_project_url":
    try:
        from supabase import create_client
        supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        logging.error(f"❌ Failed to initialize Supabase client: {e}")

BUCKET_NAME = "media"


def upload_media_to_storage(url: str, suffix: str = ".ogg") -> str:
    """
    Downloads media from Twilio and uploads it permanently to Supabase Storage.
    Returns the public URL of the uploaded file.
    If Supabase is not configured, falls back to local storage (not recommended for production).
    """
    # 1. Authenticate with Twilio to download media
    auth = None
    if os.getenv("TWILIO_ACCOUNT_SID"):
        auth = (os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
    
    response = requests.get(url, auth=auth, stream=True)
    response.raise_for_status()
    
    filename = f"{uuid.uuid4().hex}{suffix}"
    
    # 2. Upload to Supabase Storage
    if supabase_client:
        try:
            # We download to a temp file first, then upload
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                temp_path = f.name
                
            with open(temp_path, "rb") as f:
                # Upload file to Supabase bucket
                supabase_client.storage.from_(BUCKET_NAME).upload(
                    path=filename,
                    file=f,
                    file_options={"content-type": response.headers.get("Content-Type", "application/octet-stream")}
                )
                
            os.unlink(temp_path)
            
            # Get public URL
            public_url = supabase_client.storage.from_(BUCKET_NAME).get_public_url(filename)
            logging.info(f"✅ Uploaded to Supabase: {public_url}")
            return public_url
            
        except Exception as e:
            logging.error(f"❌ Supabase upload failed: {e}")
            # Fall back to local if upload fails
    
    # 3. Fallback to Local Storage (Ephemeral in Render)
    media_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "media")
    os.makedirs(media_dir, exist_ok=True)
    filepath = os.path.join(media_dir, filename)
    with open(filepath, "wb") as f:
        f.write(response.content)
    
    return f"media/{filename}"
