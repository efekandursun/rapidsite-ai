import os
from dotenv import load_dotenv
load_dotenv()
from core.database import Database
db = Database()
with db.get_connection() as conn:
    c = db._execute(conn, "SELECT * FROM webhook_jobs")
    for r in c.fetchall():
        print(dict(r))
