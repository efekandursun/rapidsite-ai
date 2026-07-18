



"""
RapidSite AI - Database Module
Supports both SQLite (development) and PostgreSQL (production via Supabase).
"""

import os
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
from dotenv import load_dotenv

load_dotenv()

# Check for PostgreSQL connection string (Supabase)
DATABASE_URL = os.getenv("DATABASE_URL")
DATABASE_PATH = os.getenv("DATABASE_PATH", "./data/rapidsite.db")

# Detect database type
USE_POSTGRES = DATABASE_URL is not None and DATABASE_URL.startswith("postgresql")


class Database:
    """Database manager supporting SQLite and PostgreSQL."""
    
    _pool = None
    
    def __init__(self, db_path: str = None):
        self.use_postgres = USE_POSTGRES
        
        try:
            if self.use_postgres:
                import psycopg
                from psycopg_pool import ConnectionPool
                from psycopg.rows import dict_row
                self.psycopg = psycopg
                self.dict_row = dict_row
                # Automatically rewrite to transaction pooler port (6543) for Supabase to prevent connection exhaustion
                import urllib.parse
                parsed = urllib.parse.urlparse(DATABASE_URL)
                netloc_parts = parsed.netloc.rsplit(':', 1)
                if len(netloc_parts) > 1 and netloc_parts[1].isdigit():
                    netloc = netloc_parts[0] + ':6543'
                else:
                    netloc = parsed.netloc + ':6543'
                self.db_url = parsed._replace(netloc=netloc).geturl()
                
                self.ConnectionPool = ConnectionPool
                print(f"🐘 Using PostgreSQL (Supabase) with psycopg3 (Lazy Pool)")
            else:
                import sqlite3
                self.sqlite3 = sqlite3
                self.db_path = db_path or DATABASE_PATH
                self._ensure_data_dir()
                print(f"📁 Using SQLite: {self.db_path}")
            
            if not self.use_postgres:
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
    
    def _get_pool(self):
        """Lazily initialize the connection pool."""
        if Database._pool is None and self.use_postgres:
            print("🔄 Initializing PostgreSQL Connection Pool...")
            Database._pool = self.ConnectionPool(
                conninfo=self.db_url,
                min_size=1,
                max_size=20,
                timeout=30.0,  # 30 seconds max waiting for a connection from pool
                kwargs={
                    "row_factory": self.dict_row,
                    "connect_timeout": 10,  # 10 seconds max waiting for TCP connection to DB
                    "prepare_threshold": None  # CRITICAL: Required for PgBouncer Transaction Mode (port 6543)
                }
            )
        return Database._pool
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections."""
        if self.use_postgres:
            pool = self._get_pool()
            with pool.connection() as conn:
                try:
                    yield conn
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
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
        if self.use_postgres:
            # Direct connection bypassing the pool for master process safety
            with self.psycopg.connect(self.db_url) as conn:
                cursor = conn.cursor()
                self._execute_schema_queries(cursor, is_postgres=True)
                conn.commit()
        else:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                self._execute_schema_queries(cursor, is_postgres=False)

    def _execute_schema_queries(self, cursor, is_postgres: bool):
        """Helper to run the schema creation queries."""
        if is_postgres:
            # PostgreSQL schema
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS companies (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    slug TEXT UNIQUE NOT NULL,
                    whatsapp_numbers TEXT,
                    procore_access_token TEXT,
                    procore_refresh_token TEXT,
                    procore_expires_at TIMESTAMP,
                    procore_company_id TEXT,
                    procore_default_project_id TEXT,
                    procore_vendors TEXT,
                    procore_cost_codes TEXT,
                    procore_locations TEXT,
                    procore_projects TEXT,
                    subscription_plan TEXT DEFAULT 'pro',
                    subscription_status TEXT DEFAULT 'trialing',
                    trial_ends_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS company_authorized_numbers (
                    id SERIAL PRIMARY KEY,
                    company_id INTEGER NOT NULL REFERENCES companies(id),
                    phone_number TEXT NOT NULL,
                    employee_name TEXT,
                    job_title TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(company_id, phone_number)
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
                    job_title TEXT,
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
                    media_paths TEXT,
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
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS webhook_jobs (
                    id SERIAL PRIMARY KEY,
                    message_sid TEXT UNIQUE NOT NULL,
                    payload TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    error TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    processed_at TIMESTAMP
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_webhook_jobs_status ON webhook_jobs(status)")
            
        else:
        # SQLite schema (original)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS companies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    slug TEXT UNIQUE NOT NULL,
                    whatsapp_numbers TEXT,
                    procore_access_token TEXT,
                    procore_refresh_token TEXT,
                    procore_expires_at TEXT,
                    procore_company_id TEXT,
                    procore_default_project_id TEXT,
                    procore_projects TEXT,
                    subscription_plan TEXT DEFAULT 'pro',
                    subscription_status TEXT DEFAULT 'trialing',
                    trial_ends_at TEXT,
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
                    job_title TEXT,
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
                CREATE TABLE IF NOT EXISTS company_authorized_numbers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_id INTEGER NOT NULL,
                    phone_number TEXT NOT NULL,
                    employee_name TEXT,
                    job_title TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (company_id) REFERENCES companies(id),
                    UNIQUE(company_id, phone_number)
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
                    media_paths TEXT,
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
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS webhook_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_sid TEXT UNIQUE NOT NULL,
                    payload TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    error TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    processed_at TEXT
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_webhook_jobs_status ON webhook_jobs(status)")

        # ADD MIGRATIONS FOR PROCORE COLUMNS IF MISSING
        try:
            # SQLite check
            if not self.use_postgres:
                cursor.execute("PRAGMA table_info(companies)")
                columns = [row['name'] for row in cursor.fetchall()]
                if 'procore_access_token' not in columns:
                    print("🔄 Migrating database: Adding Procore columns...")
                    cursor.execute("ALTER TABLE companies ADD COLUMN procore_access_token TEXT")
                    cursor.execute("ALTER TABLE companies ADD COLUMN procore_refresh_token TEXT")
                    cursor.execute("ALTER TABLE companies ADD COLUMN procore_expires_at TEXT")
                    cursor.execute("ALTER TABLE companies ADD COLUMN procore_company_id TEXT")
                    cursor.execute("ALTER TABLE companies ADD COLUMN procore_default_project_id TEXT")
            else:
                # Postgres check
                cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='companies' and column_name='procore_access_token'")
                if not cursor.fetchone():
                     print("🔄 Migrating database: Adding Procore columns (Postgres)...")
                     cursor.execute("ALTER TABLE companies ADD COLUMN procore_access_token TEXT")
                     cursor.execute("ALTER TABLE companies ADD COLUMN procore_refresh_token TEXT")
                     cursor.execute("ALTER TABLE companies ADD COLUMN procore_expires_at TIMESTAMP")
                     cursor.execute("ALTER TABLE companies ADD COLUMN procore_company_id TEXT")
                     cursor.execute("ALTER TABLE companies ADD COLUMN procore_default_project_id TEXT")
                     
        except Exception as e:
            print(f"⚠️ Error checking/migrating schema: {e}")
            
        # ADD MIGRATION FOR media_paths IF MISSING
        try:
            if not self.use_postgres:
                cursor.execute("PRAGMA table_info(site_reports)")
                columns = [row['name'] for row in cursor.fetchall()]
                if 'media_paths' not in columns:
                    cursor.execute("ALTER TABLE site_reports ADD COLUMN media_paths TEXT")
            else:
                cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='site_reports' and column_name='media_paths'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE site_reports ADD COLUMN media_paths TEXT")
        except Exception as e:
            pass
            
        # ADD MIGRATION FOR job_title IF MISSING
        try:
            if not self.use_postgres:
                cursor.execute("PRAGMA table_info(company_authorized_numbers)")
                columns = [row['name'] for row in cursor.fetchall()]
                if 'job_title' not in columns:
                    cursor.execute("ALTER TABLE company_authorized_numbers ADD COLUMN job_title TEXT")
                    
                cursor.execute("PRAGMA table_info(users)")
                columns = [row['name'] for row in cursor.fetchall()]
                if 'job_title' not in columns:
                    cursor.execute("ALTER TABLE users ADD COLUMN job_title TEXT")
            else:
                cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='company_authorized_numbers' and column_name='job_title'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE company_authorized_numbers ADD COLUMN job_title TEXT")
                    
                cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='users' and column_name='job_title'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE users ADD COLUMN job_title TEXT")
        except Exception as e:
            pass

        # ADD MIGRATION FOR SUBSCRIPTION COLUMNS
        try:
            if not self.use_postgres:
                cursor.execute("PRAGMA table_info(companies)")
                columns = [row['name'] for row in cursor.fetchall()]
                if 'subscription_plan' not in columns:
                    cursor.execute("ALTER TABLE companies ADD COLUMN subscription_plan TEXT DEFAULT 'pro'")
                if 'subscription_status' not in columns:
                    cursor.execute("ALTER TABLE companies ADD COLUMN subscription_status TEXT DEFAULT 'trialing'")
                if 'trial_ends_at' not in columns:
                    cursor.execute("ALTER TABLE companies ADD COLUMN trial_ends_at TEXT")
            else:
                cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='companies' and column_name='subscription_plan'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE companies ADD COLUMN subscription_plan TEXT DEFAULT 'pro'")
                    cursor.execute("ALTER TABLE companies ADD COLUMN subscription_status TEXT DEFAULT 'trialing'")
                    cursor.execute("ALTER TABLE companies ADD COLUMN trial_ends_at TIMESTAMP")
        except Exception as e:
            print(f"⚠️ Error migrating billing columns: {e}")



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
    
    def _decrypt_row(self, row: dict) -> dict:
        """Helper to decrypt sensitive columns if present."""
        if not row: return row
        from core.crypto import decrypt_token
        
        if 'procore_access_token' in row and row['procore_access_token']:
            row['procore_access_token'] = decrypt_token(row['procore_access_token'])
        if 'procore_refresh_token' in row and row['procore_refresh_token']:
            row['procore_refresh_token'] = decrypt_token(row['procore_refresh_token'])
        return row
        
    def _fetchone(self, cursor) -> Optional[Dict[str, Any]]:
        """Fetch one row as dictionary."""
        row = cursor.fetchone()
        if row is None:
            return None
        return self._decrypt_row(dict(row))
    
    def _fetchall(self, cursor) -> List[Dict[str, Any]]:
        """Fetch all rows as list of dictionaries."""
        rows = cursor.fetchall()
        return [self._decrypt_row(dict(row)) for row in rows]
    
    # =========================================================================
    # REPORT MANAGEMENT
    # =========================================================================
    
    def create_report(
        self,
        raw_transcript: str,
        parsed_data: dict,
        project_id: str = None,
        reported_by: str = None,
        company_id: int = None,
        media_paths: str = None
    ) -> int:
        """Create a new site report."""
        with self.get_connection() as conn:
            cursor = self._execute(conn, """
                INSERT INTO site_reports 
                (company_id, project_id, raw_transcript, parsed_data, log_type, cost_code, reported_by, media_paths)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                company_id,
                project_id,
                raw_transcript,
                json.dumps(parsed_data),
                parsed_data.get("log_type"),
                parsed_data.get("cost_code"),
                reported_by,
                media_paths
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
            
    def get_incomplete_report_for_user(self, reported_by: str) -> Optional[Dict[str, Any]]:
        """Get the most recent incomplete report for a user within the last hour."""
        with self.get_connection() as conn:
            query = """
                SELECT * FROM site_reports 
                WHERE reported_by = ? 
                AND status = 'incomplete'
                ORDER BY created_at DESC 
                LIMIT 1
            """
            cursor = self._execute(conn, query, (reported_by,))
            row = self._fetchone(cursor)
            if row:
                return self._row_to_dict(row)
            return None
            
    def update_incomplete_report(self, report_id: int, new_transcript: str, parsed_data: dict, status: str, extra_media_paths: str = None) -> bool:
        """Update an incomplete report with new transcript and data."""
        with self.get_connection() as conn:
            # First fetch existing media_paths if we have extra
            if extra_media_paths:
                cursor = self._execute(conn, "SELECT media_paths FROM site_reports WHERE id = ?", (report_id,))
                row = self._fetchone(cursor)
                if row and row['media_paths']:
                    # append them
                    try:
                        existing = json.loads(row['media_paths'])
                        new_paths = json.loads(extra_media_paths)
                        extra_media_paths = json.dumps(existing + new_paths)
                    except:
                        extra_media_paths = extra_media_paths
                        
                cursor = self._execute(conn, """
                    UPDATE site_reports 
                    SET raw_transcript = ?, 
                        parsed_data = ?, 
                        status = ?,
                        media_paths = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (new_transcript, json.dumps(parsed_data), status, extra_media_paths, report_id))
            else:
                cursor = self._execute(conn, """
                    UPDATE site_reports 
                    SET raw_transcript = ?, 
                        parsed_data = ?, 
                        status = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (new_transcript, json.dumps(parsed_data), status, report_id))
                
            return cursor.rowcount > 0
    
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
        
    def get_latest_pending_report_for_user(self, reported_by: str) -> Optional[Dict[str, Any]]:
        """Get the most recent pending report for a specific user."""
        with self.get_connection() as conn:
            cursor = self._execute(conn, """
                SELECT * FROM site_reports 
                WHERE reported_by = ? AND status = 'pending' 
                ORDER BY created_at DESC 
                LIMIT 1
            """, (reported_by,))
            row = self._fetchone(cursor)
            return self._row_to_dict(row) if row else None
    
    def update_report_parsed_data(self, report_id: int, parsed_data: Dict[str, Any]) -> bool:
        """Update the parsed JSON data of a report, and sync top-level columns."""
        import json
        with self.get_connection() as conn:
            now = datetime.utcnow().isoformat()
            
            # Extract top-level fields from parsed_data to keep columns in sync
            log_type = parsed_data.get('log_type')
            cost_code = parsed_data.get('cost_code')
            
            cursor = self._execute(conn, """
                UPDATE site_reports 
                SET parsed_data = ?,
                    log_type = ?,
                    cost_code = ?,
                    updated_at = ?
                WHERE id = ?
            """, (json.dumps(parsed_data, ensure_ascii=False), log_type, cost_code, now, report_id))
            return cursor.rowcount > 0
    
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
        """Create a new company. (Legacy whatsapp_numbers support kept for compatibility)"""
        # Calculate trial end date (14 days from now)
        trial_ends_at = datetime.utcnow() + timedelta(days=14)
        if not self.use_postgres:
            trial_ends_at = trial_ends_at.isoformat()
            
        with self.get_connection() as conn:
            cursor = self._execute(conn, """
                INSERT INTO companies (name, slug, whatsapp_numbers, subscription_plan, subscription_status, trial_ends_at)
                VALUES (?, ?, ?, 'pro', 'trialing', ?)
            """, (name, slug, whatsapp_numbers, trial_ends_at))
            
            if self.use_postgres:
                cursor.execute("SELECT lastval()")
                company_id = cursor.fetchone()['lastval']
            else:
                company_id = cursor.lastrowid
            
            # Migrate legacy numbers if provided
            if whatsapp_numbers:
                for num in whatsapp_numbers.split(','):
                    if num.strip():
                        self.add_authorized_number(company_id, num.strip(), "Initial User")
            
            # Run lightweight migrations for existing databases
            self._run_migrations(conn, cursor)
            return company_id

    def _run_migrations(self, conn, cursor):
        """Run lightweight schema migrations (e.g. adding columns)."""
        new_cols = ['procore_vendors', 'procore_cost_codes', 'procore_locations', 'procore_projects']
        for col in new_cols:
            try:
                if self.use_postgres:
                    cursor.execute(f"ALTER TABLE companies ADD COLUMN IF NOT EXISTS {col} TEXT")
                else:
                    # SQLite raises OperationalError if column exists
                    cursor.execute(f"ALTER TABLE companies ADD COLUMN {col} TEXT")
            except Exception:
                pass # Column likely already exists
        conn.commit()

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
        """Get company by WhatsApp number (checks authorized_numbers table)."""
        clean_phone = phone.replace('whatsapp:', '').strip()
        print(f"🔍 Looking for WhatsApp number: {clean_phone}")
        
        with self.get_connection() as conn:
            # Check new table first
            cursor = self._execute(conn, """
                SELECT c.*, an.employee_name, an.job_title 
                FROM companies c
                JOIN company_authorized_numbers an ON c.id = an.company_id
                WHERE an.phone_number = ?
            """, (clean_phone,))
            
            row = self._fetchone(cursor)
            
            if row:
                print(f"   ✅ Match found in authorized numbers (Employee: {row.get('employee_name')} - {row.get('job_title')})")
                return row
            
            # Fallback for + prefix issues
            cursor = self._execute(conn, """
                SELECT c.*, an.employee_name, an.job_title 
                FROM companies c
                JOIN company_authorized_numbers an ON c.id = an.company_id
                WHERE an.phone_number LIKE ?
            """, (f"%{clean_phone.lstrip('+')}",))
            
            row = self._fetchone(cursor)
            if row:
                print(f"   ✅ Match found (fuzzy search)")
                return row
                
            print(f"   ❌ No match found for {clean_phone}")
            return None
    
    def get_authorized_numbers(self, company_id: int) -> List[Dict[str, Any]]:
        """Get all authorized numbers for a company."""
        with self.get_connection() as conn:
            cursor = self._execute(conn, """
                SELECT * FROM company_authorized_numbers 
                WHERE company_id = ? 
                ORDER BY created_at DESC
            """, (company_id,))
            return self._fetchall(cursor)
    
    def add_authorized_number(self, company_id: int, phone: str, name: str = None, job_title: str = None) -> bool:
        """Add an authorized WhatsApp number."""
        clean_phone = phone.strip()
        with self.get_connection() as conn:
            try:
                self._execute(conn, """
                    INSERT INTO company_authorized_numbers (company_id, phone_number, employee_name, job_title)
                    VALUES (?, ?, ?, ?)
                """, (company_id, clean_phone, name or "Unknown User", job_title))
                return True
            except Exception as e:
                print(f"Error adding number: {e}")
                return False

    def remove_authorized_number(self, number_id: int, company_id: int) -> bool:
        """Remove an authorized number (securely scoped to company)."""
        with self.get_connection() as conn:
            cursor = self._execute(conn, """
                DELETE FROM company_authorized_numbers 
                WHERE id = ? AND company_id = ?
            """, (number_id, company_id))
            return cursor.rowcount > 0

    def update_company_numbers(self, company_id: int, numbers: str) -> bool:
        """Legacy support - updates text field but also migrates to new table."""
        # Update text field for backward compatibility
        with self.get_connection() as conn:
             self._execute(conn, """
                UPDATE companies 
                SET whatsapp_numbers = ? 
                WHERE id = ?
            """, (numbers, company_id))
        
        # Also add to new table if not exists (dumb migration)
        for num in numbers.split(','):
            if num.strip():
                # Try to add, ignore if exists (assumes employee name is unknown)
                self.add_authorized_number(company_id, num.strip(), "Migrated User")
                
        return True

    def update_company_procore_tokens(self, company_id: int, access_token: str, refresh_token: str, expires_at: int, procore_company_id: str = None) -> bool:
        """Update Procore tokens for a company."""
        from core.crypto import encrypt_token
        
        # Encrypt the tokens
        enc_access = encrypt_token(access_token)
        enc_refresh = encrypt_token(refresh_token)
        
        # Convert timestamp to ISO format
        expires_iso = datetime.fromtimestamp(expires_at).isoformat() if expires_at else None
        
        with self.get_connection() as conn:
            query = """
                UPDATE companies 
                SET procore_access_token = ?,
                    procore_refresh_token = ?,
                    procore_expires_at = ?
            """
            params = [enc_access, enc_refresh, expires_iso]
            
            if procore_company_id:
                query += ", procore_company_id = ?"
                params.append(procore_company_id)
                
            query += " WHERE id = ?"
            params.append(company_id)
            
            self._execute(conn, query, tuple(params))
            return True

    def update_company_procore_company_id(self, company_id: int, procore_company_id: str) -> bool:
        """Update Procore Company ID."""
        with self.get_connection() as conn:
            self._execute(conn, """
                UPDATE companies 
                SET procore_company_id = ? 
                WHERE id = ?
            """, (procore_company_id, company_id))
            return True

    def update_company_procore_project(self, company_id: int, project_id: str) -> bool:
        """Update default Procore project."""
        with self.get_connection() as conn:
            self._execute(conn, """
                UPDATE companies 
                SET procore_default_project_id = ? 
                WHERE id = ?
            """, (project_id, company_id))
            return True

    def update_company_procore_lists(self, company_id: int, vendors: str, cost_codes: str, locations: str) -> bool:
        """Update cached Procore lists for a company."""
        with self.get_connection() as conn:
            cursor = self._execute(conn, """
                UPDATE companies 
                SET procore_vendors = ?,
                    procore_cost_codes = ?,
                    procore_locations = ?
                WHERE id = ?
            """, (vendors, cost_codes, locations, company_id))
            return cursor.rowcount > 0

    def update_company_procore_projects(self, company_id: int, projects_json: str) -> bool:
        """Update cached Procore projects for a company."""
        with self.get_connection() as conn:
            cursor = self._execute(conn, """
                UPDATE companies 
                SET procore_projects = ?
                WHERE id = ?
            """, (projects_json, company_id))
            return cursor.rowcount > 0
    
    # =========================================================================
    # USER MANAGEMENT
    # =========================================================================
    
    def create_user(self, email: str, password_hash: str, name: str, 
                    company_id: int, role: str = 'supervisor', job_title: str = None) -> int:
        """Create a new user."""
        with self.get_connection() as conn:
            cursor = self._execute(conn, """
                INSERT INTO users (email, password_hash, name, company_id, role, job_title)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (email, password_hash, name, company_id, role, job_title))
            
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
            
            if not stored_code or stored_code != code:
                return False
            
            if not expires_at:
                return False
            
            # Parse expiry - handle string, datetime, or timezone-aware values
            if isinstance(expires_at, str):
                try:
                    expires_dt = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                except ValueError:
                    return False
            elif isinstance(expires_at, datetime):
                expires_dt = expires_at
            else:
                return False
            
            # Strip timezone for safe comparison
            if expires_dt.tzinfo is not None:
                expires_dt = expires_dt.replace(tzinfo=None)
            
            if expires_dt < datetime.now():
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
                                project_id: str = None,
                                limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """Get reports filtered by company."""
        query = "SELECT * FROM site_reports WHERE company_id = ?"
        params = [company_id]
        
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
    
    def get_all_companies(self) -> List[Dict[str, Any]]:
        """Get all companies with their basic stats for super admin dashboard."""
        with self.get_connection() as conn:
            # We fetch companies and count of users
            cursor = self._execute(conn, """
                SELECT c.*, 
                       (SELECT COUNT(*) FROM users u WHERE u.company_id = c.id) as user_count,
                       (SELECT COUNT(*) FROM site_reports r WHERE r.company_id = c.id) as report_count
                FROM companies c
                ORDER BY c.created_at DESC
            """)
            rows = self._fetchall(cursor)
            return [dict(r) for r in rows]

    def extend_company_subscription(self, company_id: int, days: int, status: str = 'active') -> bool:
        """Extend a company's subscription/trial by X days."""
        with self.get_connection() as conn:
            # First, get current trial_ends_at
            cursor = self._execute(conn, "SELECT trial_ends_at FROM companies WHERE id = ?", (company_id,))
            row = self._fetchone(cursor)
            if not row:
                return False
                
            current_end = row['trial_ends_at']
            if isinstance(current_end, str):
                # Try parsing if it's a string (SQLite often returns strings)
                try:
                    current_end = datetime.fromisoformat(current_end.replace('Z', '+00:00'))
                except ValueError:
                    # Fallback if format is different
                    current_end = None
            
            # If trial is already ended, start from today
            now = datetime.now()
            if not current_end or (isinstance(current_end, datetime) and current_end.replace(tzinfo=None) < now):
                new_end = now + timedelta(days=days)
            else:
                new_end = current_end.replace(tzinfo=None) + timedelta(days=days)
                
            self._execute(conn, 
                "UPDATE companies SET trial_ends_at = ?, subscription_status = ? WHERE id = ?",
                (new_end, status, company_id)
            )
            return True

    def _row_to_dict(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Convert database row to dictionary with parsed JSON."""
        d = dict(row)
        if d.get('parsed_data'):
            try:
                d['parsed_data'] = json.loads(d['parsed_data'])
            except (json.JSONDecodeError, TypeError):
                pass
        
        if 'media_paths' in d and d['media_paths']:
            try:
                d['media_paths'] = json.loads(d['media_paths'])
            except (json.JSONDecodeError, TypeError):
                d['media_paths'] = []
        return d

    # =========================================================================
    # QUEUE MANAGEMENT (WEBHOOK JOBS)
    # =========================================================================

    def create_webhook_job(self, message_sid: str, payload: dict) -> bool:
        """Create a new job in the queue. Returns True if created, False if duplicate."""
        with self.get_connection() as conn:
            try:
                self._execute(conn, """
                    INSERT INTO webhook_jobs (message_sid, payload)
                    VALUES (?, ?)
                """, (message_sid, json.dumps(payload)))
                return True
            except Exception as e:
                # E.g. Duplicate message_sid (UNIQUE constraint violation)
                return False

    def get_next_webhook_job(self) -> Optional[Dict[str, Any]]:
        """Atomically fetch and lock the next pending job."""
        with self.get_connection() as conn:
            if self.use_postgres:
                # Postgres supports FOR UPDATE SKIP LOCKED
                cursor = self._execute(conn, """
                    UPDATE webhook_jobs
                    SET status = 'processing'
                    WHERE id = (
                        SELECT id FROM webhook_jobs
                        WHERE status = 'pending'
                        ORDER BY created_at ASC
                        LIMIT 1
                        FOR UPDATE SKIP LOCKED
                    )
                    RETURNING *
                """)
                row = self._fetchone(cursor)
                if row:
                    row['payload'] = json.loads(row['payload'])
                    return row
            else:
                # SQLite workaround (not strictly thread-safe across processes without locking)
                cursor = self._execute(conn, """
                    SELECT * FROM webhook_jobs 
                    WHERE status = 'pending' 
                    ORDER BY created_at ASC 
                    LIMIT 1
                """)
                row = self._fetchone(cursor)
                if row:
                    self._execute(conn, "UPDATE webhook_jobs SET status = 'processing' WHERE id = ?", (row['id'],))
                    row = dict(row)
                    row['payload'] = json.loads(row['payload'])
                    return row
            return None

    def complete_webhook_job(self, job_id: int):
        """Mark job as completed."""
        with self.get_connection() as conn:
            now = datetime.utcnow().isoformat()
            self._execute(conn, """
                UPDATE webhook_jobs 
                SET status = 'completed', processed_at = ?
                WHERE id = ?
            """, (now, job_id))

    def fail_webhook_job(self, job_id: int, error_msg: str):
        """Mark job as failed with error."""
        with self.get_connection() as conn:
            now = datetime.utcnow().isoformat()
            self._execute(conn, """
                UPDATE webhook_jobs 
                SET status = 'failed', error = ?, processed_at = ?
                WHERE id = ?
            """, (error_msg, now, job_id))


# --- TEST SECTION ---
if __name__ == "__main__":
    db = Database()
    
    print("=" * 60)
    print("RapidSite AI - Database Module Test")
    print("=" * 60)
    print(f"Database type: {'PostgreSQL (Supabase)' if db.use_postgres else 'SQLite'}")
    
    # Get stats
    try:
        stats = db.get_stats()
        print(f"\n📊 Current Stats: {stats}")
        print("\n✅ Database connection successful!")
    except Exception as e:
        print(f"\n❌ Error: {e}")
