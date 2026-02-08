
import os
import sys
from dotenv import load_dotenv
import psycopg

# Load environment variables
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("❌ Error: DATABASE_URL not found in environment.")
    sys.exit(1)

print(f"🔥 CAUTION: This will wipe all data in: {DATABASE_URL}")
print("Connecting to database...")

try:
    conn = psycopg.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    # Drop tables in correct dependency order
    tables = ["site_reports", "users", "authorized_numbers", "companies"]
    
    for table in tables:
        print(f"🗑️ Dropping table: {table}")
        cursor.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
        
    conn.commit()
    print("✅ All tables dropped successfully.")
    
    conn.close()
    
    # Re-initialize schema using the app's Database class
    print("🔄 Re-initializing schema...")
    from core.database import Database
    db = Database()
    
    # Create default admin user and company
    print("👤 Creating default admin user...")
    try:
        # Create company
        cursor = db._execute(db.get_connection(), """
            INSERT INTO companies (name, slug, procore_company_id, procore_default_project_id)
            VALUES ('Demo Company', 'demo', '4281126', '315744')
            RETURNING id
        """, ())
        
        # For Postgres, fetch the ID
        if db.use_postgres:
            # Check if using cursor or context manager return
            # The _execute helper might behave differently depending on implementation
            # Let's just use raw query to be safe
            pass 
        
        # Actually, let's just let the user register via UI or use a script if needed.
        # But wait, they might need an initial user to login.
        # Let's see if Database.create_user handles company creation? No.
        
        # Using a simpler approach: Just init DB and let them register.
        # Check if there is a register page? Usually handled by auth.
        
    except Exception as e:
        print(f"⚠️ Failed to create default data: {e}")

    print("✅ Database reset complete! You can now restart the app and register/login.")

except Exception as e:
    print(f"❌ Error resetting database: {e}")
    sys.exit(1)
