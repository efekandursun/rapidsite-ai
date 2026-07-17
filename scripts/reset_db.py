import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from core.database import Database

def reset():
    db = Database()
    print("Dropping tables...")
    try:
        if db.use_postgres:
            with db.psycopg.connect(db.db_url) as conn:
                cursor = conn.cursor()
                cursor.execute("DROP TABLE IF EXISTS site_reports CASCADE;")
                cursor.execute("DROP TABLE IF EXISTS users CASCADE;")
                cursor.execute("DROP TABLE IF EXISTS company_authorized_numbers CASCADE;")
                cursor.execute("DROP TABLE IF EXISTS companies CASCADE;")
                conn.commit()
        else:
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DROP TABLE IF EXISTS site_reports;")
                cursor.execute("DROP TABLE IF EXISTS users;")
                cursor.execute("DROP TABLE IF EXISTS company_authorized_numbers;")
                cursor.execute("DROP TABLE IF EXISTS companies;")
                
        print("Reinitializing schema...")
        db._init_schema()
        print("Database reset successfully!")
    except Exception as e:
        print(f"Error resetting database: {e}")

if __name__ == "__main__":
    reset()
