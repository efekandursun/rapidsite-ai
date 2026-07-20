import os
from dotenv import load_dotenv
load_dotenv()
from core.database import Database

print("Nuking database...")
db = Database()
try:
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE site_reports, users, companies CASCADE;")
            conn.commit()
    print("✅ Database successfully wiped clean. You must register again.")
finally:
    db.pool.close()
