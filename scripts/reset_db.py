import sys
import os

# Add parent dir to path so we can import core
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import Database

def reset_db():
    print("Resetting database...")
    db = Database()
    with db.get_connection() as conn:
        cursor = conn.cursor()
        if db.use_postgres:
            print("Truncating PostgreSQL tables...")
            cursor.execute("TRUNCATE TABLE site_reports, users, company_authorized_numbers, companies RESTART IDENTITY CASCADE;")
        else:
            print("Deleting SQLite tables...")
            cursor.execute("DELETE FROM site_reports")
            cursor.execute("DELETE FROM users")
            cursor.execute("DELETE FROM company_authorized_numbers")
            cursor.execute("DELETE FROM companies")
    print("Database reset successfully.")

if __name__ == "__main__":
    reset_db()
