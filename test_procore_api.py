import os
import requests
from dotenv import load_dotenv

load_dotenv()

token = os.getenv('PROCORE_ACCESS_TOKEN') # Wait, token is in DB. Let me fetch it from DB.
