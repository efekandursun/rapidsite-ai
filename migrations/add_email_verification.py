#!/usr/bin/env python3
"""
Database migration script to add email verification columns to existing users table.
Run this once to update your existing database.
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'rapidsite.db')

def migrate():
    """Add email verification columns to users table"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'email_verified' not in columns:
            print("Adding email_verified column...")
            cursor.execute("ALTER TABLE users ADD COLUMN email_verified INTEGER DEFAULT 0")
        
        if 'verification_code' not in columns:
            print("Adding verification_code column...")
            cursor.execute("ALTER TABLE users ADD COLUMN verification_code TEXT")
        
        if 'verification_code_expires' not in columns:
            print("Adding verification_code_expires column...")
            cursor.execute("ALTER TABLE users ADD COLUMN verification_code_expires TEXT")
        
        conn.commit()
        print("✅ Migration completed successfully!")
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Migration failed: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    migrate()
