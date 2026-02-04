#!/usr/bin/env python3
"""
Migration Runner System
Automatically runs all pending migrations in order.
Tracks which migrations have been applied in migrations_applied table.
"""
import sqlite3
import os
import importlib.util
from pathlib import Path

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'fieldflow.db')
MIGRATIONS_DIR = os.path.dirname(__file__)

def ensure_migrations_table():
    """Create migrations_applied table if it doesn't exist"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS migrations_applied (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            migration_name TEXT UNIQUE NOT NULL,
            applied_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    conn.close()

def get_applied_migrations():
    """Get list of already applied migrations"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT migration_name FROM migrations_applied ORDER BY id")
    applied = [row[0] for row in cursor.fetchall()]
    
    conn.close()
    return set(applied)

def mark_migration_applied(migration_name):
    """Mark a migration as applied"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute(
        "INSERT INTO migrations_applied (migration_name) VALUES (?)",
        (migration_name,)
    )
    
    conn.commit()
    conn.close()

def run_migrations():
    """Run all pending migrations in numerical order"""
    ensure_migrations_table()
    applied = get_applied_migrations()
    
    # Find all migration files
    migration_files = sorted([
        f for f in os.listdir(MIGRATIONS_DIR)
        if f.endswith('.py') and f[0].isdigit() and f != 'migrate.py'
    ])
    
    if not migration_files:
        print("No migration files found.")
        return
    
    pending_migrations = [m for m in migration_files if m not in applied]
    
    if not pending_migrations:
        print(f"✅ All migrations up to date ({len(applied)} applied)")
        return
    
    print(f"Found {len(pending_migrations)} pending migration(s)...")
    print()
    
    for migration_file in pending_migrations:
        migration_path = os.path.join(MIGRATIONS_DIR, migration_file)
        migration_name = migration_file
        
        print(f"Running: {migration_name}")
        print("-" * 50)
        
        try:
            # Load and execute migration module
            spec = importlib.util.spec_from_file_location("migration", migration_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Run migrate function
            if hasattr(module, 'migrate'):
                module.migrate()
                mark_migration_applied(migration_name)
            else:
                print(f"⚠️  {migration_name} has no migrate() function")
                
        except Exception as e:
            print(f"❌ Failed to run {migration_name}: {e}")
            print("   Stopping migration process.")
            break
        
        print()
    
    print("=" * 50)
    print(f"✅ Migration process complete!")
    applied_after = get_applied_migrations()
    print(f"   Total migrations applied: {len(applied_after)}")

if __name__ == '__main__':
    run_migrations()
