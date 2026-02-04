"""
FieldFlow AI - Database Module
Supports both SQLite (development) and PostgreSQL (production via Supabase).
"""

import os
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
from dotenv import load_dotenv

load_dotenv()

# Check for PostgreSQL connection string (Supabase)
DATABASE_URL = os.getenv("DATABASE_URL")
DATABASE_PATH = os.getenv("DATABASE_PATH", "./data/fieldflow.db")

# Detect database type
USE_POSTGRES = DATABASE_URL is not None and DATABASE_URL.startswith("postgresql")


class Database:
    """Database manager supporting SQLite and PostgreSQL."""
    
    def __init__(self, db_path: str = None):
        self.use_postgres = USE_POSTGRES
        
        try:
            if self.use_postgres:
                import psycopg
                from psycopg.rows import dict_row
                self.psycopg = psycopg
                self.dict_row = dict_row
                self.db_url = DATABASE_URL
                print(f"🐘 Using PostgreSQL (Supabase) with psycopg3")
            else:
                import sqlite3
                self.sqlite3 = sqlite3
                self.db_path = db_path or DATABASE_PATH
                self._ensure_data_dir()
                print(f"📁 Using SQLite: {self.db_path}")
            
            self._init_schema()
        except Exception as e:
            print(f"❌ Database initialization error: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    def _ensure_data_dir(self):
        """Create data directory if it doesn't exist (SQLite only)."""
        if not self.use_postgres:
            data_dir = os.path.dirname(self.db_path)
            if data_dir and not os.path.exists(data_dir):
                os.makedirs(data_dir)
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections."""
        if self.use_postgres:
            conn = self.psycopg.connect(self.db_url, row_factory=self.dict_row)
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
        else:
            conn = self.sqlite3.connect(self.db_path)
            conn.row_factory = self.sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
    
    def _placeholder(self, index: int = None) -> str:
        """Return the correct placeholder for the database type."""
        if self.use_postgres:
            return "%s"
        return "?"
    
    def _init_schema(self):
        """Initialize database schema."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            if self.use_postgres:
                # PostgreSQL schema
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS companies (
                        id SERIAL PRIMARY KEY,
                        name TEXT NOT NULL,
                        slug TEXT UNIQUE NOT NULL,
                        whatsapp_numbers TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id SERIAL PRIMARY KEY,
                        email TEXT UNIQUE NOT NULL,
                        password_hash TEXT NOT NULL,
                        name TEXT NOT NULL,
                        company_id INTEGER REFERENCES companies(id),
                        role TEXT DEFAULT 'supervisor',
                        is_active INTEGER DEFAULT 1,
                        email_verified INTEGER DEFAULT 0,
                        verification_code TEXT,
                        verification_code_expires TEXT,
                        whatsapp_number TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS site_reports (
                        id SERIAL PRIMARY KEY,
                        company_id INTEGER REFERENCES companies(id),
                        project_id TEXT,
                        raw_transcript TEXT NOT NULL,
                        parsed_data TEXT NOT NULL,
                        log_type TEXT,
                        cost_code TEXT,
                        status TEXT DEFAULT 'pending',
                        erp_synced INTEGER DEFAULT 0,
                        erp_sync_id TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        reported_by TEXT,
                        approved_by TEXT,
                        approved_at TIMESTAMP
                    )
                """)
                
                # Create indexes (PostgreSQL syntax)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_reports_status ON site_reports(status)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_reports_company ON site_reports(company_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
                
            else:
                # SQLite schema (original)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS companies (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        slug TEXT UNIQUE NOT NULL,
                        whatsapp_numbers TEXT,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        email TEXT UNIQUE NOT NULL,
                        password_hash TEXT NOT NULL,
                        name TEXT NOT NULL,
                        company_id INTEGER,
                        role TEXT DEFAULT 'supervisor',
                        is_active INTEGER DEFAULT 1,
                        email_verified INTEGER DEFAULT 0,
                        verification_code TEXT,
                        verification_code_expires TEXT,
                        whatsapp_number TEXT,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (company_id) REFERENCES companies(id)
                    )
                """)
                
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS site_reports (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        company_id INTEGER,
                        project_id TEXT,
                        raw_transcript TEXT NOT NULL,
                        parsed_data TEXT NOT NULL,
                        log_type TEXT,
                        cost_code TEXT,
                        status TEXT DEFAULT 'pending',
                        erp_synced INTEGER DEFAULT 0,
                        erp_sync_id TEXT,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        reported_by TEXT,
                        approved_by TEXT,
                        approved_at TEXT,
                        FOREIGN KEY (company_id) REFERENCES companies(id)
                    )
                """)
                
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_reports_status ON site_reports(status)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_reports_company ON site_reports(company_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
    
    def _execute(self, conn, query: str, params: tuple = None):
        """Execute query with proper placeholder replacement."""
        if self.use_postgres:
            cursor = conn.cursor()
            # Replace ? with %s for PostgreSQL
            query = query.replace("?", "%s")
        else:
            cursor = conn.cursor()
        
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        return cursor
    
    def _fetchone(self, cursor) -> Optional[Dict[str, Any]]:
        """Fetch one row as dictionary."""
        row = cursor.fetchone()
        if row is None:
            return None
        if self.use_postgres:
            return dict(row)
        return dict(row)
    
    def _fetchall(self, cursor) -> List[Dict[str, Any]]:
        """Fetch all rows as list of dictionaries."""
        rows = cursor.fetchall()
        if self.use_postgres:
            return [dict(row) for row in rows]
        return [dict(row) for row in rows]
    
    # =========================================================================
    # REPORT MANAGEMENT
    # =========================================================================
    
    def create_report(
        self,
        raw_transcript: str,
        parsed_data: dict,
        project_id: str = None,
        reported_by: str = None,
        company_id: int = None
    ) -> int:
        """Create a new site report."""
        with self.get_connection() as conn:
            cursor = self._execute(conn, """
                INSERT INTO site_reports 
                (company_id, project_id, raw_transcript, parsed_data, log_type, cost_code, reported_by)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                company_id,
                project_id,
                raw_transcript,
                json.dumps(parsed_data),
                parsed_data.get("log_type"),
                parsed_data.get("cost_code"),
                reported_by
            ))
            
            if self.use_postgres:
                # Get last inserted ID for PostgreSQL
                cursor.execute("SELECT lastval()")
                return cursor.fetchone()['lastval']
            return cursor.lastrowid
    
    def get_report(self, report_id: int) -> Optional[Dict[str, Any]]:
        """Get a single report by ID."""
        with self.get_connection() as conn:
            cursor = self._execute(conn, 
                "SELECT * FROM site_reports WHERE id = ?", 
                (report_id,)
            )
            row = self._fetchone(cursor)
            if row:
                return self._row_to_dict(row)
            return None
    
    def get_reports(
        self,
        status: str = None,
        project_id: str = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get reports with optional filtering."""
        query = "SELECT * FROM site_reports WHERE 1=1"
        params = []
        
        if status:
            query += " AND status = ?"
            params.append(status)
        
        if project_id:
            query += " AND project_id = ?"
            params.append(project_id)
        
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        with self.get_connection() as conn:
            cursor = self._execute(conn, query, tuple(params))
            rows = self._fetchall(cursor)
            return [self._row_to_dict(row) for row in rows]
    
    def get_pending_reports(self) -> List[Dict[str, Any]]:
        """Get all pending reports for approval."""
        return self.get_reports(status="pending")
    
    def approve_report(self, report_id: int, approved_by: str = None) -> bool:
        """Approve a pending report."""
        with self.get_connection() as conn:
            now = datetime.utcnow().isoformat()
            cursor = self._execute(conn, """
                UPDATE site_reports 
                SET status = 'approved', 
                    approved_by = ?,
                    approved_at = ?,
                    updated_at = ?
                WHERE id = ? AND status = 'pending'
            """, (approved_by, now, now, report_id))
            return cursor.rowcount > 0
    
    def reject_report(self, report_id: int, reason: str = None) -> bool:
        """Reject a pending report."""
        with self.get_connection() as conn:
            cursor = self._execute(conn, """
                UPDATE site_reports 
                SET status = 'rejected',
                    updated_at = ?
                WHERE id = ? AND status = 'pending'
            """, (datetime.utcnow().isoformat(), report_id))
            return cursor.rowcount > 0
    
    def mark_synced(self, report_id: int, erp_sync_id: str = None) -> bool:
        """Mark report as synced to ERP."""
        with self.get_connection() as conn:
            cursor = self._execute(conn, """
                UPDATE site_reports 
                SET erp_synced = 1,
                    erp_sync_id = ?,
                    status = 'synced',
                    updated_at = ?
                WHERE id = ?
            """, (erp_sync_id, datetime.utcnow().isoformat(), report_id))
            return cursor.rowcount > 0
    
    def get_stats(self) -> Dict[str, int]:
        """Get report statistics."""
        with self.get_connection() as conn:
            stats = {}
            for status in ['pending', 'approved', 'rejected', 'synced']:
                cursor = self._execute(conn,
                    "SELECT COUNT(*) as count FROM site_reports WHERE status = ?",
                    (status,)
                )
                row = self._fetchone(cursor)
                stats[status] = row['count'] if row else 0
            
            stats['total'] = sum(stats.values())
            return stats
    
    # =========================================================================
    # COMPANY MANAGEMENT
    # =========================================================================
    
    def create_company(self, name: str, slug: str, whatsapp_numbers: str = None) -> int:
        """Create a new company."""
        with self.get_connection() as conn:
            cursor = self._execute(conn, """
                INSERT INTO companies (name, slug, whatsapp_numbers)
                VALUES (?, ?, ?)
            """, (name, slug, whatsapp_numbers))
            
            if self.use_postgres:
                cursor.execute("SELECT lastval()")
                return cursor.fetchone()['lastval']
            return cursor.lastrowid
    
    def get_company(self, company_id: int) -> Optional[Dict[str, Any]]:
        """Get company by ID."""
        with self.get_connection() as conn:
            cursor = self._execute(conn,
                "SELECT * FROM companies WHERE id = ?", (company_id,)
            )
            return self._fetchone(cursor)
    
    def get_company_by_slug(self, slug: str) -> Optional[Dict[str, Any]]:
        """Get company by slug."""
        with self.get_connection() as conn:
            cursor = self._execute(conn,
                "SELECT * FROM companies WHERE slug = ?", (slug,)
            )
            return self._fetchone(cursor)
    
    def get_company_by_whatsapp(self, phone: str) -> Optional[Dict[str, Any]]:
        """Get company by WhatsApp number."""
        # Normalize phone number
        clean_phone = phone.replace('whatsapp:', '').strip()
        print(f"🔍 Looking for WhatsApp number: {clean_phone} (original: {phone})")
        
        with self.get_connection() as conn:
            cursor = self._execute(conn, "SELECT * FROM companies")
            rows = self._fetchall(cursor)
            for row in rows:
                numbers = row.get('whatsapp_numbers') or ''
                print(f"   Checking company '{row.get('name')}': numbers='{numbers}'")
                
                # Check various formats
                if clean_phone in numbers:
                    print(f"   ✅ Match found!")
                    return row
                # Also try without + prefix
                if clean_phone.lstrip('+') in numbers.replace('+', ''):
                    print(f"   ✅ Match found (without +)!")
                    return row
                    
            print(f"   ❌ No match found for {clean_phone}")
            return None
    
    def update_company_numbers(self, company_id: int, numbers: str) -> bool:
        """Update authorized WhatsApp numbers for a company."""
        with self.get_connection() as conn:
            cursor = self._execute(conn, """
                UPDATE companies 
                SET whatsapp_numbers = ? 
                WHERE id = ?
            """, (numbers, company_id))
            return cursor.rowcount > 0
    
    # =========================================================================
    # USER MANAGEMENT
    # =========================================================================
    
    def create_user(self, email: str, password_hash: str, name: str, 
                    company_id: int, role: str = 'supervisor') -> int:
        """Create a new user."""
        with self.get_connection() as conn:
            cursor = self._execute(conn, """
                INSERT INTO users (email, password_hash, name, company_id, role)
                VALUES (?, ?, ?, ?, ?)
            """, (email, password_hash, name, company_id, role))
            
            if self.use_postgres:
                cursor.execute("SELECT lastval()")
                return cursor.fetchone()['lastval']
            return cursor.lastrowid
    
    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get user by email."""
        with self.get_connection() as conn:
            cursor = self._execute(conn,
                "SELECT * FROM users WHERE email = ? AND is_active = 1", 
                (email,)
            )
            return self._fetchone(cursor)
    
    def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user by ID."""
        with self.get_connection() as conn:
            cursor = self._execute(conn,
                "SELECT * FROM users WHERE id = ? AND is_active = 1", 
                (user_id,)
            )
            return self._fetchone(cursor)
    
    def get_user_by_whatsapp(self, phone: str) -> Optional[Dict[str, Any]]:
        """Get user by WhatsApp number."""
        clean_phone = phone.replace('whatsapp:', '')
        with self.get_connection() as conn:
            cursor = self._execute(conn,
                "SELECT * FROM users WHERE whatsapp_number = ? AND is_active = 1",
                (clean_phone,)
            )
            return self._fetchone(cursor)
    
    def update_user_whatsapp(self, user_id: int, phone: str) -> bool:
        """Update user's WhatsApp number."""
        with self.get_connection() as conn:
            cursor = self._execute(conn, """
                UPDATE users 
                SET whatsapp_number = ? 
                WHERE id = ?
            """, (phone, user_id))
            return cursor.rowcount > 0
    
    def get_users_by_company(self, company_id: int) -> List[Dict[str, Any]]:
        """Get all users for a company."""
        with self.get_connection() as conn:
            cursor = self._execute(conn,
                "SELECT * FROM users WHERE company_id = ? AND is_active = 1 ORDER BY created_at DESC",
                (company_id,)
            )
            return self._fetchall(cursor)
    
    def set_verification_code(self, email: str, code: str, expires_at: str) -> bool:
        """Set verification code for user."""
        with self.get_connection() as conn:
            cursor = self._execute(conn, """
                UPDATE users 
                SET verification_code = ?, verification_code_expires = ?
                WHERE email = ?
            """, (code, expires_at, email))
            return cursor.rowcount > 0
    
    def verify_email(self, email: str, code: str) -> bool:
        """Verify email with code and activate account."""
        with self.get_connection() as conn:
            cursor = self._execute(conn,
                "SELECT verification_code, verification_code_expires FROM users WHERE email = ?",
                (email,)
            )
            row = self._fetchone(cursor)
            
            if not row:
                return False
            
            stored_code = row.get('verification_code')
            expires_at = row.get('verification_code_expires')
            
            if stored_code != code:
                return False
            
            if datetime.fromisoformat(expires_at) < datetime.now():
                return False
            
            self._execute(conn, """
                UPDATE users 
                SET email_verified = 1, verification_code = NULL, verification_code_expires = NULL
                WHERE email = ?
            """, (email,))
            
            return True
    
    # =========================================================================
    # COMPANY-FILTERED DATA ACCESS
    # =========================================================================
    
    def get_reports_by_company(self, company_id: int, status: str = None,
                                limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """Get reports filtered by company."""
        query = "SELECT * FROM site_reports WHERE company_id = ?"
        params = [company_id]
        
        if status:
            query += " AND status = ?"
            params.append(status)
        
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        with self.get_connection() as conn:
            cursor = self._execute(conn, query, tuple(params))
            rows = self._fetchall(cursor)
            return [self._row_to_dict(row) for row in rows]
    
    def get_stats_by_company(self, company_id: int) -> Dict[str, int]:
        """Get report statistics for a specific company."""
        with self.get_connection() as conn:
            stats = {}
            for status in ['pending', 'approved', 'rejected', 'synced']:
                cursor = self._execute(conn,
                    "SELECT COUNT(*) as count FROM site_reports WHERE company_id = ? AND status = ?",
                    (company_id, status)
                )
                row = self._fetchone(cursor)
                stats[status] = row['count'] if row else 0
            
            stats['total'] = sum(stats.values())
            return stats
    
    def _row_to_dict(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Convert database row to dictionary with parsed JSON."""
        d = dict(row)
        if d.get('parsed_data'):
            try:
                d['parsed_data'] = json.loads(d['parsed_data'])
            except (json.JSONDecodeError, TypeError):
                pass
        return d


# --- TEST SECTION ---
if __name__ == "__main__":
    db = Database()
    
    print("=" * 60)
    print("FieldFlow AI - Database Module Test")
    print("=" * 60)
    print(f"Database type: {'PostgreSQL (Supabase)' if db.use_postgres else 'SQLite'}")
    
    # Get stats
    try:
        stats = db.get_stats()
        print(f"\n📊 Current Stats: {stats}")
        print("\n✅ Database connection successful!")
    except Exception as e:
        print(f"\n❌ Error: {e}")
