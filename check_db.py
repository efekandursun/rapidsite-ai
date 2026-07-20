import os
from dotenv import load_dotenv
load_dotenv()
from core.database import Database

db = Database()
with db.get_connection() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT email FROM users;")
        print(cur.fetchall())
