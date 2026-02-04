#!/usr/bin/env python3
"""
Migration 003: Add Audit Trail Columns
Adds updated_at, updated_by, and deleted_at to all tables for change tracking.
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'fieldflow.db')

def migrate():
    """Add audit trail columns to all tables"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        print("Adding audit trail columns...")
        
        # Get existing columns for each table
        tables = ['users', 'companies', 'site_reports']
        audit_columns = [
            ('updated_at', 'TEXT'),
            ('updated_by', 'INTEGER'),  # User ID who made the change
            ('deleted_at', 'TEXT')       # NULL = active, timestamp = soft deleted
        ]
        
        for table in tables:
            cursor.execute(f"PRAGMA table_info({table})")
            existing_columns = [col[1] for col in cursor.fetchall()]
            
            for col_name, col_type in audit_columns:
                if col_name not in existing_columns:
                    cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")
                    print(f"✓ {table}.{col_name}")
        
        conn.commit()
        print("\n✅ Migration 003 completed successfully!")
        print("   Audit trail columns added (updated_at, updated_by, deleted_at)")
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Migration failed: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    migrate()
