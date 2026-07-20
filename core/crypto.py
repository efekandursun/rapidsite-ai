import os
from cryptography.fernet import Fernet
import logging

def get_cipher():
    """Get the Fernet cipher suite based on ENCRYPTION_KEY env var."""
    key = os.getenv('ENCRYPTION_KEY')
    if not key:
        if os.getenv("FLASK_ENV") == "production":
            logging.error("CRITICAL SECURITY ERROR: ENCRYPTION_KEY is missing in production environment!")
            raise ValueError("ENCRYPTION_KEY must be set in production to prevent data loss on restarts.")
            
        # Fallback for environments where ENCRYPTION_KEY is missing
        logging.warning("⚠️ ENCRYPTION_KEY not set in environment. Using a deterministic fallback key derived from DB URL.")
        import hashlib
        import base64
        stable_seed = os.getenv('DATABASE_URL') or os.getenv('SUPABASE_URL') or 'fallback-local-dev-seed-123'
        key_hash = hashlib.sha256(stable_seed.encode('utf-8')).digest()
        key = base64.urlsafe_b64encode(key_hash).decode('utf-8')
        os.environ['ENCRYPTION_KEY'] = key
    
    try:
        return Fernet(key.encode('utf-8') if isinstance(key, str) else key)
    except Exception as e:
        logging.error(f"Failed to initialize Fernet cipher: {e}")
        return None

def encrypt_token(token: str) -> str:
    """Encrypt a plain text token."""
    if not token:
        return token
    # If it's already encrypted (starts with gAAAAA), return as is
    if token.startswith('gAAAAA'):
        return token
        
    cipher = get_cipher()
    if cipher:
        try:
            return cipher.encrypt(token.encode('utf-8')).decode('utf-8')
        except Exception as e:
            logging.error(f"Encryption failed: {e}")
            return token # Fallback to plain if encrypt fails
    return token

def decrypt_token(encrypted_token: str) -> str:
    """Decrypt an encrypted token."""
    if not encrypted_token:
        return encrypted_token
    # If it's not encrypted (doesn't start with gAAAAA), return as is
    if not encrypted_token.startswith('gAAAAA'):
        return encrypted_token
        
    cipher = get_cipher()
    if cipher:
        try:
            return cipher.decrypt(encrypted_token.encode('utf-8')).decode('utf-8')
        except Exception as e:
            logging.error(f"Decryption failed: {e}")
            return encrypted_token # Fallback to encrypted string
    return encrypted_token
