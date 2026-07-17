import os
import psycopg
from dotenv import load_dotenv

load_dotenv()
conn = psycopg.connect(os.getenv("DATABASE_URL"))
conn.autocommit = True
try:
    conn.execute("ALTER TABLE companies ADD COLUMN subscription_plan TEXT DEFAULT 'pro'")
    print("subscription_plan added.")
except Exception as e:
    print(e)
try:
    conn.execute("ALTER TABLE companies ADD COLUMN subscription_status TEXT DEFAULT 'trialing'")
    print("subscription_status added.")
except Exception as e:
    print(e)
try:
    conn.execute("ALTER TABLE companies ADD COLUMN trial_ends_at TIMESTAMP")
    print("trial_ends_at added.")
except Exception as e:
    print(e)

print("Done")
