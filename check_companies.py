import os
from dotenv import load_dotenv
load_dotenv()
from core.database import Database

db = Database()
with db.get_connection() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT id, name, procore_access_token FROM companies;")
        print(cur.fetchall())
