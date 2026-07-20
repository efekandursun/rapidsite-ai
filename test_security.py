import os
import unittest
import json
from flask import Flask
from app import app, db
from core.database import Database

class SecurityTestSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Configure app for testing
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False # For regular API testing, though we will test CSRF explicitly
        cls.client = app.test_client()
        
        # Disable Twilio/OpenAI real calls for test
        os.environ['TWILIO_AUTH_TOKEN'] = 'test_token'
        
        # Create a test company and user
        cls.test_company_id = db.create_company("Security Test LLC", "sectest-slug", "+10000000000")
        cls.victim_company_id = db.create_company("Victim LLC", "victim-slug", "+10000000001")
        
        cls.test_user_id = db.create_user("attacker@test.com", "hash", "Attacker", cls.test_company_id, "admin", "Admin")
        cls.victim_user_id = db.create_user("victim@test.com", "hash", "Victim", cls.victim_company_id, "admin", "Admin")
        
        # Create a report in victim company
        cls.victim_report_id = db.create_report(
            "Victim's private report", 
            {"events": [{"log_type": "notes", "description": "Secret info"}]},
            "PRJ-1",
            "+10000000001",
            cls.victim_company_id
        )

    def login(self, email):
        with self.client.session_transaction() as sess:
            user = db.get_user_by_email(email)
            sess['user_id'] = user['id']
            sess['company_id'] = user['company_id']
            sess['role'] = user['role']

    def test_1_idor_protection(self):
        """Test that Attacker cannot read Victim's report via API."""
        self.login("attacker@test.com")
        
        response = self.client.get(f'/api/v1/reports/{self.victim_report_id}')
        # Should be 404 because get_authorized_report returns None when company doesn't match
        self.assertEqual(response.status_code, 404)
        
        response_approve = self.client.post(f'/dashboard/approve/{self.victim_report_id}')
        # /dashboard routes redirect to /dashboard if report not found
        self.assertEqual(response_approve.status_code, 302)
        
        print("✅ IDOR Protection Passed: Attacker blocked from Victim's report.")

    def test_2_webhook_spoofing(self):
        """Test that missing Twilio auth token blocks the request."""
        # Remove token
        os.environ['TWILIO_AUTH_TOKEN'] = ''
        response = self.client.post('/webhook/whatsapp', data={"From": "+10000000000", "Body": "Spoofed"})
        self.assertEqual(response.status_code, 403)
        print("✅ Webhook Spoofing Passed: Missing token returns 403 Forbidden.")
        os.environ['TWILIO_AUTH_TOKEN'] = 'test_token'

    def test_3_privilege_escalation(self):
        """Test that normal admin cannot create super_admin user."""
        self.login("attacker@test.com")
        
        response = self.client.post('/settings/team/add', data={
            'name': 'Hacker',
            'email': 'hacker2@test.com',
            'role': 'super_admin',
            'password': 'password123'
        })
        
        # Check if the user was created as supervisor instead of super_admin
        created_user = db.get_user_by_email('hacker2@test.com')
        self.assertIsNotNone(created_user)
        self.assertEqual(created_user['role'], 'supervisor')
        print("✅ Privilege Escalation Passed: Forged 'super_admin' role downgraded to 'supervisor'.")

    def test_4_csrf_protection(self):
        """Test CSRF enforcement on POST forms."""
        # Enable CSRF for this specific test
        app.config['WTF_CSRF_ENABLED'] = True
        
        # Attempt POST without CSRF token
        response = self.client.post('/settings/numbers/add', data={
            'employee_name': 'Test',
            'phone_number': '+11234567890'
        })
        
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"The CSRF token is missing", response.data)
        print("✅ CSRF Protection Passed: Missing token returns 400 Bad Request.")
        app.config['WTF_CSRF_ENABLED'] = False

if __name__ == '__main__':
    print("\n" + "🛡️"*25)
    print("🛡️ RUNNING SECURITY EXPLOIT TEST SUITE 🛡️")
    print("🛡️"*25 + "\n")
    unittest.main()
