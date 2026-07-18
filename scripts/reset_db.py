import os
from dotenv import load_dotenv

# Load env before importing database
load_dotenv()

from core.database import Database
import psycopg

def reset():
    print("⚠️  WARNING: Resetting PostgreSQL Database...")
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("❌ DATABASE_URL not found!")
        return
        
    print(f"🔗 Connecting to: {db_url.split('@')[1]}")
    
    # Connect directly to run DROP statements
    with psycopg.connect(db_url) as conn:
        cursor = conn.cursor()
        print("🗑️  Dropping tables...")
        cursor.execute("""
            DROP TABLE IF EXISTS webhook_jobs CASCADE;
            DROP TABLE IF EXISTS site_reports CASCADE;
            DROP TABLE IF EXISTS company_authorized_numbers CASCADE;
            DROP TABLE IF EXISTS users CASCADE;
            DROP TABLE IF EXISTS companies CASCADE;
        """)
        conn.commit()
        print("✅ Tables dropped.")
        
    # Re-initialize schema
    print("🏗️  Recreating schema...")
    db = Database()
    db._init_schema()
    print("✅ Database successfully reset and schema recreated!")

if __name__ == "__main__":
    reset()
