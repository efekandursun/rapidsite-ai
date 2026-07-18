import os
from cryptography.fernet import Fernet
import logging

def get_cipher():
    """Get the Fernet cipher suite based on ENCRYPTION_KEY env var."""
    key = os.getenv('ENCRYPTION_KEY')
    if not key:
        # Fallback for development, but warns the user
        logging.warning("⚠️ ENCRYPTION_KEY not set in environment. Using a temporary key. Tokens will be lost on restart.")
        key = Fernet.generate_key()
        os.environ['ENCRYPTION_KEY'] = key.decode()
    
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
