import os
import psycopg
from dotenv import load_dotenv
load_dotenv()

conn = psycopg.connect(os.getenv("DATABASE_URL"))
conn.autocommit = True
with conn.cursor() as cur:
    cur.execute("TRUNCATE site_reports, users, companies CASCADE;")
print("NUKED!")
conn.close()
