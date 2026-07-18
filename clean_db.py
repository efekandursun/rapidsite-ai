import os
from dotenv import load_dotenv
load_dotenv()
from core.database import Database

db = Database()
with db.get_connection() as conn:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM site_reports;")
        deleted = cur.rowcount
    conn.commit()

print(f"Deleted {deleted} reports from site_reports.")
