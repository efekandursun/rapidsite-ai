"""
Migration 005: Add Authorized Numbers Table
Adds a dedicated table for managing authorized WhatsApp numbers with employee names.
"""

import sqlite3

def upgrade(conn):
    """Add company_authorized_numbers table."""
    print("  → Creating company_authorized_numbers table...")
    
    # Check if connection is PostgreSQL (psycopg connection)
    is_postgres = hasattr(conn, 'info') 
    
    if is_postgres:
        # PostgreSQL Syntax
        conn.execute("""
            CREATE TABLE IF NOT EXISTS company_authorized_numbers (
                id SERIAL PRIMARY KEY,
                company_id INTEGER NOT NULL REFERENCES companies(id),
                phone_number TEXT NOT NULL,
                employee_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(company_id, phone_number)
            )
        """)
    else:
        # SQLite Syntax
        conn.execute("""
            CREATE TABLE IF NOT EXISTS company_authorized_numbers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id INTEGER NOT NULL,
                phone_number TEXT NOT NULL,
                employee_name TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (company_id) REFERENCES companies(id),
                UNIQUE(company_id, phone_number)
            )
        """)
    
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_auth_numbers_company 
        ON company_authorized_numbers(company_id)
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_auth_numbers_phone 
        ON company_authorized_numbers(phone_number)
    """)
    
    print("  ✓ Created company_authorized_numbers table")

def downgrade(conn):
    """Drop company_authorized_numbers table."""
    print("  → Dropping company_authorized_numbers table...")
    conn.execute("DROP TABLE IF EXISTS company_authorized_numbers")
    pass

if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    db_url = os.getenv("DATABASE_URL")
    
    if db_url and db_url.startswith("postgresql"):
        print("🐘 Applying migration to PostgreSQL...")
        import psycopg
        try:
            conn = psycopg.connect(db_url)
            upgrade(conn)
            conn.commit()
            print("✓ Migration 005 applied successfully (PostgreSQL)")
            conn.close()
        except Exception as e:
            print(f"✗ Migration failed: {e}")
    else:
        print("📁 Applying migration to SQLite...")
        db_path = "data/rapidsite.db"
        conn = sqlite3.connect(db_path)
        
        try:
            upgrade(conn)
            conn.commit()
            print("✓ Migration 005 applied successfully (SQLite)")
        except Exception as e:
            print(f"✗ Migration 005 failed: {e}")
            conn.rollback()
        finally:
            conn.close()
