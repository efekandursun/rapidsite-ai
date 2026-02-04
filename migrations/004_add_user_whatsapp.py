"""
Migration 004: Add WhatsApp number to users table
Allows tracking which user sent which report
"""

import sqlite3


def upgrade(conn):
    """Add whatsapp_number column to users table."""
    print("  → Adding whatsapp_number to users table...")
    
    conn.execute("""
        ALTER TABLE users 
        ADD COLUMN whatsapp_number TEXT
    """)
    
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_whatsapp 
        ON users(whatsapp_number)
    """)
    
    print("  ✓ User WhatsApp number column added")


def downgrade(conn):
    """Remove whatsapp_number column (SQLite doesn't support DROP COLUMN easily)."""
    print("  → Removing whatsapp_number not supported in SQLite")
    pass


if __name__ == "__main__":
    db_path = "data/fieldflow.db"
    conn = sqlite3.connect(db_path)
    
    try:
        upgrade(conn)
        conn.commit()
        print("✓ Migration 004 applied successfully")
    except Exception as e:
        print(f"✗ Migration 004 failed: {e}")
        conn.rollback()
    finally:
        conn.close()
