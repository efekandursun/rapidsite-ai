"""
RapidSite AI - Comprehensive Test Suite
========================================
Tests cover:
    1. Auth Module (password hashing, login_required, slugify)
    2. Database Module (CRUD: companies, users, reports, authorized numbers)
    3. Brain Module (AI parsing, system prompt generation)
    4. WhatsApp Handler (webhook, idempotency, message formatting, TwiML extraction)
    5. Mailer Module (verification code generation)
    6. Connectors (CSV Export, Procore init)
    7. Utils (retry decorator)
    8. App Routes (landing, pricing, privacy, terms, health, dashboard auth, API auth)
    9. CSRF & Rate Limiting presence
"""

import os
import sys
import json
import time
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock, PropertyMock
from datetime import datetime, timedelta

# Ensure project root is on path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

# Set required env vars BEFORE importing app modules
os.environ.setdefault('FLASK_SECRET_KEY', 'test-secret-key-for-unit-tests')
os.environ.setdefault('FLASK_ENV', 'development')
os.environ.setdefault('PASSWORD_SALT', 'test-salt')
os.environ.setdefault('OPENAI_API_KEY', 'sk-test-fake-key-for-unit-tests')

# Remove DATABASE_URL so tests use SQLite
if 'DATABASE_URL' in os.environ:
    _original_db_url = os.environ.pop('DATABASE_URL')
else:
    _original_db_url = None


# ============================================================================
# 1. AUTH MODULE TESTS
# ============================================================================

class TestAuthModule(unittest.TestCase):
    """Tests for core/auth.py - password hashing, verification, helpers."""

    def test_hash_password_returns_bcrypt(self):
        """hash_password should return a bcrypt hash starting with $2b$."""
        from core.auth import hash_password
        hashed = hash_password("TestPassword123")
        self.assertTrue(hashed.startswith("$2b$"), f"Expected bcrypt hash, got: {hashed[:10]}")

    def test_hash_password_unique_salts(self):
        """Two calls to hash_password with the same input should produce different hashes."""
        from core.auth import hash_password
        h1 = hash_password("same_password")
        h2 = hash_password("same_password")
        self.assertNotEqual(h1, h2, "bcrypt should use unique salts")

    def test_verify_password_correct(self):
        """verify_password should return True for the correct password."""
        from core.auth import hash_password, verify_password
        pw = "CorrectPassword!"
        hashed = hash_password(pw)
        self.assertTrue(verify_password(pw, hashed))

    def test_verify_password_incorrect(self):
        """verify_password should return False for a wrong password."""
        from core.auth import hash_password, verify_password
        hashed = hash_password("CorrectPassword!")
        self.assertFalse(verify_password("WrongPassword!", hashed))

    def test_verify_password_legacy_sha256(self):
        """verify_password should handle legacy SHA-256 hashes."""
        import hashlib
        from core.auth import verify_password
        salt = os.getenv('PASSWORD_SALT', 'rapidsite-default-salt')
        pw = "legacy_password"
        legacy_hash = hashlib.sha256(f"{pw}{salt}".encode()).hexdigest()
        self.assertTrue(verify_password(pw, legacy_hash))
        self.assertFalse(verify_password("wrong", legacy_hash))

    def test_slugify(self):
        """slugify should produce URL-friendly slugs."""
        from core.auth import slugify
        self.assertEqual(slugify("ABC Construction Inc."), "abc-construction-inc")
        self.assertEqual(slugify("  Spaces  Here  "), "spaces-here")
        self.assertEqual(slugify("Special!@#Characters"), "specialcharacters")

    def test_slugify_empty(self):
        from core.auth import slugify
        self.assertEqual(slugify(""), "")


# ============================================================================
# 2. DATABASE MODULE TESTS
# ============================================================================

class TestDatabaseModule(unittest.TestCase):
    """Tests for core/database.py using an in-memory SQLite database."""

    def setUp(self):
        """Create a fresh SQLite database for each test."""
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test.db")
        
        # Force SQLite mode
        import core.database as db_module
        db_module.USE_POSTGRES = False
        db_module.DATABASE_PATH = self.db_path
        
        from core.database import Database
        self.db = Database(db_path=self.db_path)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_create_company(self):
        """Should create a company and return its ID."""
        cid = self.db.create_company(name="Test Corp", slug="test-corp")
        self.assertIsNotNone(cid)
        self.assertIsInstance(cid, int)

    def test_get_company(self):
        """Should retrieve a company by ID."""
        cid = self.db.create_company(name="Acme", slug="acme")
        company = self.db.get_company(cid)
        self.assertIsNotNone(company)
        self.assertEqual(company['name'], "Acme")
        self.assertEqual(company['slug'], "acme")

    def test_get_company_by_slug(self):
        """Should retrieve a company by slug."""
        self.db.create_company(name="Slug Corp", slug="slug-corp")
        company = self.db.get_company_by_slug("slug-corp")
        self.assertIsNotNone(company)
        self.assertEqual(company['name'], "Slug Corp")

    def test_get_company_by_slug_not_found(self):
        result = self.db.get_company_by_slug("nonexistent")
        self.assertIsNone(result)

    def test_create_user(self):
        """Should create a user linked to a company."""
        cid = self.db.create_company(name="UserCo", slug="userco")
        uid = self.db.create_user(
            email="test@example.com",
            password_hash="$2b$12$fakehash",
            name="Test User",
            company_id=cid,
            role="admin"
        )
        self.assertIsNotNone(uid)

    def test_get_user_by_email(self):
        """Should find user by email (case insensitive in practice)."""
        cid = self.db.create_company(name="FindCo", slug="findco")
        self.db.create_user(
            email="find@test.com",
            password_hash="hash123",
            name="Find Me",
            company_id=cid,
            role="supervisor"
        )
        user = self.db.get_user_by_email("find@test.com")
        self.assertIsNotNone(user)
        self.assertEqual(user['name'], "Find Me")

    def test_get_user_by_email_not_found(self):
        result = self.db.get_user_by_email("nobody@nowhere.com")
        self.assertIsNone(result)

    def test_create_report(self):
        """Should create a site report."""
        cid = self.db.create_company(name="ReportCo", slug="reportco")
        rid = self.db.create_report(
            raw_transcript="Poured 100 CY concrete today",
            parsed_data={"log_type": "production", "item": "Concrete", "quantity": 100},
            project_id="PRJ-001",
            reported_by="Field Worker",
            company_id=cid
        )
        self.assertIsNotNone(rid)

    def test_get_report(self):
        """Should retrieve a report by ID."""
        cid = self.db.create_company(name="GetReportCo", slug="getreportco")
        rid = self.db.create_report(
            raw_transcript="Rebar delivery",
            parsed_data={"log_type": "delivery"},
            project_id="PRJ-002",
            reported_by="Worker",
            company_id=cid
        )
        report = self.db.get_report(rid)
        self.assertIsNotNone(report)
        self.assertEqual(report['raw_transcript'], "Rebar delivery")

    def test_approve_report(self):
        """Approving a pending report should succeed."""
        cid = self.db.create_company(name="ApproveCo", slug="approveco")
        rid = self.db.create_report(
            raw_transcript="test",
            parsed_data={"log_type": "notes"},
            reported_by="w",
            company_id=cid
        )
        result = self.db.approve_report(rid, approved_by="Supervisor")
        self.assertTrue(result)
        report = self.db.get_report(rid)
        self.assertEqual(report['status'], 'approved')

    def test_approve_report_already_approved(self):
        """Approving an already-approved report should fail."""
        cid = self.db.create_company(name="DoubleAppCo", slug="doubleappco")
        rid = self.db.create_report(
            raw_transcript="t",
            parsed_data={},
            reported_by="w",
            company_id=cid
        )
        self.db.approve_report(rid, "S1")
        result = self.db.approve_report(rid, "S2")
        self.assertFalse(result)

    def test_reject_report(self):
        """Rejecting a pending report should succeed."""
        cid = self.db.create_company(name="RejectCo", slug="rejectco")
        rid = self.db.create_report(
            raw_transcript="bad data",
            parsed_data={},
            reported_by="w",
            company_id=cid
        )
        result = self.db.reject_report(rid)
        self.assertTrue(result)
        report = self.db.get_report(rid)
        self.assertEqual(report['status'], 'rejected')

    def test_mark_synced(self):
        """mark_synced should update ERP sync status."""
        cid = self.db.create_company(name="SyncCo", slug="syncco")
        rid = self.db.create_report(
            raw_transcript="sync me",
            parsed_data={},
            reported_by="w",
            company_id=cid
        )
        result = self.db.mark_synced(rid, erp_sync_id="PROCORE-12345")
        self.assertTrue(result)
        report = self.db.get_report(rid)
        self.assertEqual(report['status'], 'synced')
        self.assertEqual(report['erp_sync_id'], 'PROCORE-12345')

    def test_get_stats(self):
        """get_stats should return correct counts."""
        cid = self.db.create_company(name="StatsCo", slug="statsco")
        # Create 3 pending reports
        for _ in range(3):
            self.db.create_report(raw_transcript="t", parsed_data={}, reported_by="w", company_id=cid)
        stats = self.db.get_stats()
        self.assertEqual(stats['pending'], 3)
        self.assertEqual(stats['total'], 3)

    def test_add_authorized_number(self):
        """Should add an authorized WhatsApp number."""
        cid = self.db.create_company(name="NumCo", slug="numco")
        self.db.add_authorized_number(cid, "+15551234567", "John Doe", "Foreman")
        numbers = self.db.get_authorized_numbers(cid)
        self.assertEqual(len(numbers), 1)
        self.assertEqual(numbers[0]['phone_number'], "+15551234567")
        self.assertEqual(numbers[0]['employee_name'], "John Doe")

    def test_get_company_by_whatsapp(self):
        """Should find company by authorized WhatsApp number."""
        cid = self.db.create_company(name="WhatsAppCo", slug="whatsappco")
        self.db.add_authorized_number(cid, "+15559876543", "Jane")
        company = self.db.get_company_by_whatsapp("+15559876543")
        self.assertIsNotNone(company)
        self.assertEqual(company['name'], "WhatsAppCo")

    def test_get_company_by_whatsapp_with_prefix(self):
        """Should strip 'whatsapp:' prefix when searching."""
        cid = self.db.create_company(name="PrefixCo", slug="prefixco")
        self.db.add_authorized_number(cid, "+15551111111", "Bob")
        company = self.db.get_company_by_whatsapp("whatsapp:+15551111111")
        self.assertIsNotNone(company)

    def test_company_trial_period(self):
        """New companies should have a 14-day trial."""
        cid = self.db.create_company(name="TrialCo", slug="trialco")
        company = self.db.get_company(cid)
        self.assertIsNotNone(company.get('trial_ends_at'))
        self.assertEqual(company['subscription_plan'], 'pro')
        self.assertEqual(company['subscription_status'], 'trialing')

    def test_verification_code_flow(self):
        """Should set and verify email verification codes."""
        cid = self.db.create_company(name="VerifyCo", slug="verifyco")
        self.db.create_user(
            email="verify@test.com",
            password_hash="hash",
            name="Verify User",
            company_id=cid,
            role="admin"
        )
        expires = (datetime.now() + timedelta(minutes=15)).isoformat()
        self.db.set_verification_code("verify@test.com", "123456", expires)
        
        # Correct code
        result = self.db.verify_email("verify@test.com", "123456")
        self.assertTrue(result)
        
        # After verification, user should be verified
        user = self.db.get_user_by_email("verify@test.com")
        self.assertEqual(user['email_verified'], 1)


# ============================================================================
# 3. BRAIN MODULE TESTS
# ============================================================================

class TestBrainModule(unittest.TestCase):
    """Tests for core/brain.py - AI parsing engine."""

    def test_system_prompt_base(self):
        """System prompt should contain construction terminology."""
        with patch('openai.OpenAI'):
            from core.brain import ConstructionBrain
            brain = ConstructionBrain()
            prompt = brain.get_system_prompt()
            self.assertIn("construction", prompt.lower())
            self.assertIn("JSON ARRAY", prompt)
            self.assertIn("log_type", prompt)
            self.assertIn("cost_code", prompt)

    def test_system_prompt_with_master_data(self):
        """System prompt should include Procore master data when provided."""
        with patch('openai.OpenAI'):
            from core.brain import ConstructionBrain
            brain = ConstructionBrain()
            company = {
                'procore_vendors': '[{"id": 1, "name": "Acme Concrete"}]',
                'procore_cost_codes': '[{"id": 1, "full_code": "03-30-00", "name": "Concrete"}]',
                'procore_locations': '[{"id": 1, "name": "Building A"}]'
            }
            prompt = brain.get_system_prompt(company)
            self.assertIn("MASTER DATA", prompt)
            self.assertIn("Acme Concrete", prompt)
            self.assertIn("03-30-00", prompt)
            self.assertIn("Building A", prompt)

    def test_system_prompt_without_master_data(self):
        """System prompt should NOT include master data section for empty company."""
        with patch('openai.OpenAI'):
            from core.brain import ConstructionBrain
            brain = ConstructionBrain()
            company = {'procore_vendors': '[]', 'procore_cost_codes': '[]', 'procore_locations': '[]'}
            prompt = brain.get_system_prompt(company)
            self.assertNotIn("MASTER DATA", prompt)

    @patch('openai.OpenAI')
    def test_parse_text_success(self, mock_openai_cls):
        """parse_text should return parsed JSON from the LLM."""
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps([{
            "log_type": "production",
            "item": "Concrete Pour",
            "quantity": 150,
            "unit": "CY",
            "status": "complete"
        }])
        mock_client.chat.completions.create.return_value = mock_response
        
        from core.brain import ConstructionBrain
        brain = ConstructionBrain()
        result = brain.parse_text("We poured 150 yards of concrete today")
        
        self.assertIsInstance(result, list)
        self.assertEqual(result[0]['log_type'], 'production')
        self.assertEqual(result[0]['quantity'], 150)

    @patch('openai.OpenAI')
    def test_parse_text_strips_markdown(self, mock_openai_cls):
        """parse_text should handle markdown-wrapped JSON responses."""
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '```json\n[{"log_type": "notes"}]\n```'
        mock_client.chat.completions.create.return_value = mock_response
        
        from core.brain import ConstructionBrain
        brain = ConstructionBrain()
        result = brain.parse_text("General note")
        self.assertEqual(result[0]['log_type'], 'notes')

    @patch('openai.OpenAI')
    def test_parse_text_invalid_json_raises(self, mock_openai_cls):
        """parse_text should raise ParsingError on invalid JSON."""
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "This is not JSON at all"
        mock_client.chat.completions.create.return_value = mock_response
        
        from core.brain import ConstructionBrain, ParsingError
        brain = ConstructionBrain()
        with self.assertRaises(ParsingError):
            brain.parse_text("something")

    @patch('openai.OpenAI')
    def test_transcribe_audio(self, mock_openai_cls):
        """transcribe_audio should call Whisper and return text."""
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        
        mock_transcript = MagicMock()
        mock_transcript.text = "We poured concrete at Building A"
        mock_client.audio.transcriptions.create.return_value = mock_transcript
        
        from core.brain import ConstructionBrain
        brain = ConstructionBrain()
        
        # Create a temporary audio file
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
            f.write(b"fake audio data")
            audio_path = f.name
        
        try:
            result = brain.transcribe_audio(audio_path)
            self.assertEqual(result, "We poured concrete at Building A")
        finally:
            os.unlink(audio_path)

    def test_exception_classes(self):
        """TranscriptionError and ParsingError should be proper exceptions."""
        from core.brain import TranscriptionError, ParsingError
        self.assertTrue(issubclass(TranscriptionError, Exception))
        self.assertTrue(issubclass(ParsingError, Exception))


# ============================================================================
# 4. WHATSAPP HANDLER TESTS
# ============================================================================

class TestWhatsAppHandler(unittest.TestCase):
    """Tests for core/whatsapp_handler.py - utility functions."""

    def test_extract_project_id_standard(self):
        """Should extract PRJ-XXX format project IDs."""
        from core.whatsapp_handler import extract_project_id
        self.assertEqual(extract_project_id("Working on PRJ-001 today"), "PRJ-001")
        self.assertEqual(extract_project_id("PROJECT-123 is great"), "PRJ-123")
        self.assertEqual(extract_project_id("PROJ42 done"), "PRJ-42")

    def test_extract_project_id_none(self):
        """Should return None when no project ID is found."""
        from core.whatsapp_handler import extract_project_id
        self.assertIsNone(extract_project_id("Just a normal message"))
        self.assertIsNone(extract_project_id(""))

    def test_extract_body_from_twiml(self):
        """Should extract body text from TwiML XML."""
        from core.whatsapp_handler import extract_body_from_twiml
        twiml = '<Response><Message><Body>Hello World</Body></Message></Response>'
        self.assertEqual(extract_body_from_twiml(twiml), "Hello World")

    def test_extract_body_from_twiml_nested(self):
        """Should handle TwiML with only <Message> tags."""
        from core.whatsapp_handler import extract_body_from_twiml
        twiml = '<Response><Message>Plain text</Message></Response>'
        self.assertEqual(extract_body_from_twiml(twiml), "Plain text")

    def test_extract_body_from_twiml_no_match(self):
        """Should return None for non-TwiML text."""
        from core.whatsapp_handler import extract_body_from_twiml
        self.assertIsNone(extract_body_from_twiml("just plain text"))

    def test_format_confirmation_complete(self):
        """format_confirmation should produce a readable confirmation."""
        from core.whatsapp_handler import format_confirmation
        result = {
            'parsed_data_list': [{
                'status': 'complete',
                'log_type': 'production',
                'item': 'Concrete',
                'quantity': 100,
                'unit': 'CY',
                'cost_code': '03-30-00'
            }],
            'report_ids': [42],
            'company_name': 'Test Corp'
        }
        msg = format_confirmation(result)
        self.assertIn("Report(s) Received", msg)
        self.assertIn("#42", msg)
        self.assertIn("Concrete", msg)
        self.assertIn("100", msg)

    def test_format_confirmation_incomplete(self):
        """Should show follow-up question for incomplete reports."""
        from core.whatsapp_handler import format_confirmation
        result = {
            'parsed_data_list': [{
                'status': 'incomplete',
                'follow_up_question': 'How many workers were on site?'
            }],
            'report_ids': [1],
            'company_name': 'Test'
        }
        msg = format_confirmation(result)
        self.assertIn("MISSING INFO", msg)
        self.assertIn("How many workers", msg)

    def test_format_confirmation_empty(self):
        """Should handle empty parsed data gracefully."""
        from core.whatsapp_handler import format_confirmation
        result = {'parsed_data_list': [], 'report_ids': [], 'company_name': 'X'}
        msg = format_confirmation(result)
        self.assertIn("could not be processed", msg)

    def test_idempotency_cache(self):
        """_purge_old_sids should remove expired entries."""
        from core.whatsapp_handler import processed_sids, _purge_old_sids
        # Add an old entry
        processed_sids['old_sid'] = time.time() - 7200  # 2 hours ago
        processed_sids['new_sid'] = time.time()
        
        _purge_old_sids(ttl_seconds=3600)
        
        self.assertNotIn('old_sid', processed_sids)
        self.assertIn('new_sid', processed_sids)
        
        # Cleanup
        processed_sids.pop('new_sid', None)


# ============================================================================
# 5. MAILER MODULE TESTS
# ============================================================================

class TestMailerModule(unittest.TestCase):
    """Tests for core/mailer.py."""

    def test_generate_verification_code_format(self):
        """Verification code should be a 6-digit string."""
        from core.mailer import generate_verification_code
        for _ in range(100):
            code = generate_verification_code()
            self.assertEqual(len(code), 6)
            self.assertTrue(code.isdigit())

    def test_generate_verification_code_range(self):
        """Code should be between 100000 and 999999."""
        from core.mailer import generate_verification_code
        codes = set()
        for _ in range(50):
            code = int(generate_verification_code())
            self.assertGreaterEqual(code, 100000)
            self.assertLessEqual(code, 999999)
            codes.add(code)
        # Should have some variety
        self.assertGreater(len(codes), 1)


# ============================================================================
# 6. CONNECTORS TESTS
# ============================================================================

class TestCSVExportConnector(unittest.TestCase):
    """Tests for connectors/csv_export.py."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        from connectors.csv_export import CSVExportConnector
        self.connector = CSVExportConnector({"export_path": self.test_dir})

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_name(self):
        self.assertEqual(self.connector.name, "CSV Export")

    def test_authenticate(self):
        self.assertTrue(self.connector.authenticate())

    def test_test_connection(self):
        self.assertTrue(self.connector.test_connection())

    def test_get_projects_empty(self):
        self.assertEqual(self.connector.get_projects(), [])

    def test_push_daily_log(self):
        """Should create a CSV file with the report data."""
        data = {
            "log_type": "production",
            "item": "Concrete Pour",
            "quantity": 150,
            "unit": "CY",
            "cost_code": "03-30-00",
            "description": "Test pour",
            "urgency": "normal",
            "location": {"building": "A", "level": "2"},
            "crew": {"count": 8, "trade": "Concrete"},
            "equipment": ["Pump Truck"]
        }
        result = self.connector.push_daily_log("PRJ-001", data)
        self.assertTrue(result['success'])
        self.assertIn("CSV-", result['erp_id'])
        self.assertTrue(os.path.exists(result['file_path']))
        
        # Verify CSV content
        with open(result['file_path'], 'r') as f:
            content = f.read()
            self.assertIn("Concrete Pour", content)
            self.assertIn("150", content)

    def test_push_multiple_logs(self):
        """Should append to existing CSV file."""
        data1 = {"log_type": "production", "item": "Concrete"}
        data2 = {"log_type": "delivery", "item": "Rebar"}
        
        r1 = self.connector.push_daily_log("PRJ-001", data1)
        r2 = self.connector.push_daily_log("PRJ-001", data2)
        
        # Both should write to the same file (same project, same day)
        self.assertEqual(r1['file_path'], r2['file_path'])

    def test_flatten_data(self):
        """_flatten_data should handle nested dicts."""
        data = {
            "log_type": "manpower",
            "location": {"building": "B", "level": "3", "area": "North"},
            "crew": {"count": 5, "trade": "Electrical"},
            "equipment": ["Crane", "Forklift"]
        }
        flat = self.connector._flatten_data(data)
        self.assertEqual(flat['location_building'], "B")
        self.assertEqual(flat['crew_count'], 5)
        self.assertIn("Crane", flat['equipment'])

    def test_get_all_exports(self):
        """get_all_exports should list CSV files."""
        self.connector.push_daily_log("PRJ-001", {"log_type": "notes"})
        exports = self.connector.get_all_exports()
        self.assertEqual(len(exports), 1)
        self.assertTrue(exports[0].endswith('.csv'))


class TestProcoreConnectorInit(unittest.TestCase):
    """Tests for Procore connector initialization."""

    def test_procore_name(self):
        from connectors.procore import ProcoreConnector
        conn = ProcoreConnector({'client_id': 'test', 'client_secret': 'test'})
        self.assertEqual(conn.name, "Procore")

    def test_procore_production_url(self):
        from connectors.procore import ProcoreConnector
        conn = ProcoreConnector({'use_sandbox': False})
        self.assertEqual(conn.base_url, "https://api.procore.com")

    def test_procore_sandbox_url(self):
        from connectors.procore import ProcoreConnector
        conn = ProcoreConnector({'use_sandbox': True})
        self.assertEqual(conn.base_url, "https://sandbox.procore.com")

    def test_procore_headers(self):
        from connectors.procore import ProcoreConnector
        conn = ProcoreConnector({
            'access_token': 'test-token',
            'company_id': '12345'
        })
        headers = conn.headers
        self.assertEqual(headers['Authorization'], 'Bearer test-token')
        self.assertEqual(headers['Procore-Company-Id'], '12345')

    def test_procore_auth_url(self):
        from connectors.procore import ProcoreConnector
        conn = ProcoreConnector({
            'client_id': 'my-client',
            'redirect_uri': 'https://example.com/callback'
        })
        url = conn.get_auth_url()
        self.assertIn("my-client", url)
        self.assertIn("example.com/callback", url)


class TestERPBaseClasses(unittest.TestCase):
    """Test base ERP classes and exceptions."""

    def test_erp_error_hierarchy(self):
        from connectors.base import ERPError, AuthenticationError, ConnectionError, SyncError
        self.assertTrue(issubclass(AuthenticationError, ERPError))
        self.assertTrue(issubclass(ConnectionError, ERPError))
        self.assertTrue(issubclass(SyncError, ERPError))

    def test_base_transform_data(self):
        """Default transform_data should return data as-is."""
        from connectors.csv_export import CSVExportConnector
        conn = CSVExportConnector({"export_path": tempfile.mkdtemp()})
        data = {"foo": "bar"}
        self.assertEqual(conn.transform_data(data), data)


# ============================================================================
# 7. UTILS TESTS
# ============================================================================

class TestRetryDecorator(unittest.TestCase):
    """Tests for core/utils.py - retry_on_exception."""

    def test_retry_succeeds_first_try(self):
        """Should not retry if the function succeeds."""
        from core.utils import retry_on_exception
        
        call_count = 0
        
        @retry_on_exception(exceptions=(ValueError,), max_retries=3, initial_delay=0.01)
        def succeeds():
            nonlocal call_count
            call_count += 1
            return "ok"
        
        result = succeeds()
        self.assertEqual(result, "ok")
        self.assertEqual(call_count, 1)

    def test_retry_succeeds_after_failures(self):
        """Should retry and succeed on the third attempt."""
        from core.utils import retry_on_exception
        
        call_count = 0
        
        @retry_on_exception(exceptions=(ValueError,), max_retries=3, initial_delay=0.01, backoff_factor=1.0)
        def fails_twice():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("not yet")
            return "done"
        
        result = fails_twice()
        self.assertEqual(result, "done")
        self.assertEqual(call_count, 3)

    def test_retry_exhausts_all_retries(self):
        """Should raise after max_retries exhausted."""
        from core.utils import retry_on_exception
        
        @retry_on_exception(exceptions=(RuntimeError,), max_retries=2, initial_delay=0.01, backoff_factor=1.0)
        def always_fails():
            raise RuntimeError("always broken")
        
        with self.assertRaises(RuntimeError):
            always_fails()

    def test_retry_only_catches_specified_exceptions(self):
        """Should not retry on exceptions not in the exceptions tuple."""
        from core.utils import retry_on_exception
        
        @retry_on_exception(exceptions=(ValueError,), max_retries=3, initial_delay=0.01)
        def raises_type_error():
            raise TypeError("wrong type")
        
        with self.assertRaises(TypeError):
            raises_type_error()


# ============================================================================
# 8. APP ROUTE TESTS
# ============================================================================

class TestAppRoutes(unittest.TestCase):
    """Tests for app.py - Flask routes (public pages, auth guards, APIs)."""

    @classmethod
    def setUpClass(cls):
        """Create Flask test client."""
        # Patch Database to use SQLite for tests
        test_dir = tempfile.mkdtemp()
        cls._test_dir = test_dir
        db_path = os.path.join(test_dir, "test_app.db")
        
        import core.database as db_module
        db_module.USE_POSTGRES = False
        db_module.DATABASE_PATH = db_path
        
        from app import app
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False  # Disable CSRF for testing
        app.config['SERVER_NAME'] = 'localhost'
        cls.app = app
        cls.client = app.test_client()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._test_dir, ignore_errors=True)

    def test_landing_page(self):
        """GET / should return 200."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'RapidSite', response.data)

    def test_pricing_page(self):
        """GET /pricing should return 200."""
        response = self.client.get('/pricing')
        self.assertEqual(response.status_code, 200)

    def test_privacy_page(self):
        """GET /privacy should return 200."""
        response = self.client.get('/privacy')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Privacy Policy', response.data)

    def test_terms_page(self):
        """GET /terms should return 200."""
        response = self.client.get('/terms')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Terms of Service', response.data)

    def test_health_endpoint(self):
        """GET /health should return JSON with status healthy."""
        response = self.client.get('/health')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'healthy')

    def test_login_page_get(self):
        """GET /login should return the login form."""
        response = self.client.get('/login')
        self.assertEqual(response.status_code, 200)

    def test_register_page_get(self):
        """GET /register should return the registration form."""
        response = self.client.get('/register')
        self.assertEqual(response.status_code, 200)

    def test_dashboard_requires_login(self):
        """GET /dashboard without auth should redirect to login."""
        response = self.client.get('/dashboard', follow_redirects=False)
        self.assertIn(response.status_code, [302, 303])

    def test_settings_requires_login(self):
        """GET /settings without auth should redirect to login."""
        response = self.client.get('/settings', follow_redirects=False)
        self.assertIn(response.status_code, [302, 303])

    def test_api_reports_requires_login(self):
        """GET /api/v1/reports without auth should redirect."""
        response = self.client.get('/api/v1/reports', follow_redirects=False)
        self.assertIn(response.status_code, [302, 303])

    def test_api_stats_requires_login(self):
        """GET /api/v1/stats without auth should redirect."""
        response = self.client.get('/api/v1/stats', follow_redirects=False)
        self.assertIn(response.status_code, [302, 303])

    def test_logout_clears_session(self):
        """GET /logout should redirect to login."""
        response = self.client.get('/logout', follow_redirects=False)
        self.assertIn(response.status_code, [302, 303])

    def test_login_empty_credentials(self):
        """POST /login with empty fields should show error."""
        response = self.client.post('/login', data={
            'email': '',
            'password': ''
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

    def test_login_wrong_credentials(self):
        """POST /login with wrong credentials should show error."""
        response = self.client.post('/login', data={
            'email': 'wrong@test.com',
            'password': 'wrongpassword'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

    def test_register_password_mismatch(self):
        """POST /register with mismatched passwords should show error."""
        response = self.client.post('/register', data={
            'company_name': 'Test Co',
            'name': 'Test User',
            'email': 'mismatch@test.com',
            'password': 'password123',
            'confirm_password': 'different456'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

    def test_register_short_password(self):
        """POST /register with short password should show error."""
        response = self.client.post('/register', data={
            'company_name': 'Test Co',
            'name': 'Test User',
            'email': 'short@test.com',
            'password': 'abc',
            'confirm_password': 'abc'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)

    def test_404_page(self):
        """Non-existent route should return 404."""
        response = self.client.get('/nonexistent-page-that-does-not-exist')
        self.assertEqual(response.status_code, 404)


# ============================================================================
# 9. SECURITY CONFIGURATION TESTS
# ============================================================================

class TestSecurityConfig(unittest.TestCase):
    """Test that security middleware is properly configured."""

    def test_csrf_protection_loaded(self):
        """CSRF protection should be initialized."""
        from app import csrf
        self.assertIsNotNone(csrf)

    def test_rate_limiter_loaded(self):
        """Rate limiter should be initialized."""
        from app import limiter
        self.assertIsNotNone(limiter)

    def test_session_cookie_httponly(self):
        """Session cookie should be HttpOnly."""
        from app import app
        self.assertTrue(app.config.get('SESSION_COOKIE_HTTPONLY'))

    def test_session_cookie_samesite(self):
        """Session cookie should have SameSite=Lax."""
        from app import app
        self.assertEqual(app.config.get('SESSION_COOKIE_SAMESITE'), 'Lax')

    def test_session_lifetime(self):
        """Session lifetime should be 24 hours."""
        from app import app
        self.assertEqual(app.config.get('PERMANENT_SESSION_LIFETIME'), 86400)

    def test_secret_key_set(self):
        """Flask secret key should be set."""
        from app import app
        self.assertIsNotNone(app.secret_key)
        self.assertNotEqual(app.secret_key, '')


# ============================================================================
# MAIN
# ============================================================================

if __name__ == '__main__':
    print("=" * 70)
    print("🏗️  RapidSite AI - Comprehensive Test Suite")
    print("=" * 70)
    
    # Run all tests with verbosity
    unittest.main(verbosity=2)
