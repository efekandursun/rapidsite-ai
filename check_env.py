import os
print(f"FLASK_ENV: {os.getenv('FLASK_ENV')}")
print(f"ENCRYPTION_KEY exists: {'ENCRYPTION_KEY' in os.environ}")
