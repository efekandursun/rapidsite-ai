#!/usr/bin/env python3
"""
Migration 002: Add Performance Indexes
Adds indexes to frequently queried columns for 10-100x performance improvement.
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'rapidsite.db')

def migrate():
    """Add performance indexes to database"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        print("Creating performance indexes...")
        
        # Users table indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
        print("✓ idx_users_email")
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_company_id ON users(company_id)")
        print("✓ idx_users_company_id")
        
        # Companies table indexes  
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_companies_slug ON companies(slug)")
        print("✓ idx_companies_slug")
        
        # Site reports indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_site_reports_company_id ON site_reports(company_id)")
        print("✓ idx_site_reports_company_id")
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_site_reports_status ON site_reports(status)")
        print("✓ idx_site_reports_status")
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_site_reports_created_at ON site_reports(created_at DESC)")
        print("✓ idx_site_reports_created_at")
        
        conn.commit()
        print("\n✅ Migration 002 completed successfully!")
        print("   6 indexes created for performance optimization")
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Migration failed: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    migrate()
