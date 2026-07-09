from core.database import Database
db = Database()

print("--- Authorized Numbers ---")
with db.get_connection() as conn:
    if db.use_postgres:
        res = conn.execute("SELECT * FROM company_authorized_numbers").fetchall()
        for r in res: print(r)

print("\n--- Recent Reports ---")
with db.get_connection() as conn:
    if db.use_postgres:
        res = conn.execute("SELECT id, created_at, status, raw_transcript FROM site_reports ORDER BY created_at DESC LIMIT 5").fetchall()
        for r in res: print(r)
