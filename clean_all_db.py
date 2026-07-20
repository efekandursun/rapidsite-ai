import os
from dotenv import load_dotenv
import psycopg

load_dotenv()
DB_URL = os.getenv("DATABASE_URL")

print(f"Connecting to {DB_URL.split('@')[1]}...")
with psycopg.connect(DB_URL) as conn:
    with conn.cursor() as cur:
        print("Truncating all tables...")
        cur.execute("TRUNCATE TABLE webhook_jobs, site_reports, company_authorized_numbers, users, companies RESTART IDENTITY CASCADE;")
        conn.commit()
print("✅ Database COMPLETELY nuked and reset to zero.")
