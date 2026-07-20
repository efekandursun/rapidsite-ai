import requests
import os
import uuid
import psycopg
import re

BASE_URL = "https://rapidsite.app"
DB_URL = "postgresql://postgres.pudumoqwovtostypddaj:Baboliyim5775.@aws-1-us-west-1.pooler.supabase.com:5432/postgres"

session = requests.Session()
session.headers.update({"Referer": BASE_URL})

def get_csrf(url):
    res = session.get(url)
    match = re.search(r'<input type="hidden" name="csrf_token" value="([^"]+)"/?>', res.text)
    if match:
        return match.group(1)
    return ""

def run_tests():
    uid = str(uuid.uuid4())[:8]
    email = f"test_{uid}@example.com"
    password = "TestPassword123!"
    company_name = f"Test Corp {uid}"
    
    print(f"--- Starting E2E Test against {BASE_URL} ---")
    print(f"1. Registering user {email} for company {company_name}")
    
    csrf = get_csrf(f"{BASE_URL}/register")
    res = session.post(f"{BASE_URL}/register", data={
        "csrf_token": csrf,
        "name": "Test User",
        "email": email,
        "company_name": company_name,
        "password": password,
        "confirm_password": password,
        "agree_tos": "y"
    }, allow_redirects=False)
    
    print(f"Register status: {res.status_code}")
    if res.status_code >= 400:
        print(f"Failed to register. {res.text[:200]}")
        return
        
    print("2. Fetching verification code from DB...")
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT verification_code, company_id FROM users WHERE email = %s", (email,))
            row = cur.fetchone()
            if not row:
                print("❌ User not found in DB!")
                return
            code = row[0]
            company_id = row[1]
            print(f"Got code: {code}")
            
    print("3. Verifying email...")
    csrf = get_csrf(f"{BASE_URL}/verify-email")
    res = session.post(f"{BASE_URL}/verify-email", data={
        "csrf_token": csrf,
        "email": email,
        "code": code
    }, allow_redirects=False)
    print(f"Verify status: {res.status_code}")
    
    print("4. Logging in...")
    csrf = get_csrf(f"{BASE_URL}/login")
    res = session.post(f"{BASE_URL}/login", data={
        "csrf_token": csrf,
        "email": email,
        "password": password
    }, allow_redirects=False)
    print(f"Login status: {res.status_code}")
    
    print("5. Accessing dashboard...")
    res = session.get(f"{BASE_URL}/dashboard")
    print(f"Dashboard status: {res.status_code}")
    if "Dashboard" in res.text or company_name in res.text:
        print("✅ Dashboard loaded successfully!")
    else:
        print("❌ Dashboard content mismatch.")
        
    print("6. Requesting password reset...")
    csrf = get_csrf(f"{BASE_URL}/forgot-password")
    res = session.post(f"{BASE_URL}/forgot-password", data={
        "csrf_token": csrf,
        "email": email
    }, allow_redirects=False)
    print(f"Forgot password status: {res.status_code}")
    
    print("7. Fetching reset token from DB...")
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT reset_token FROM users WHERE email = %s", (email,))
            row = cur.fetchone()
            reset_token = row[0]
            print(f"Got reset token: {reset_token}")
            
    print("8. Resetting password...")
    csrf = get_csrf(f"{BASE_URL}/reset-password/{reset_token}")
    new_password = "NewPassword456!"
    res = session.post(f"{BASE_URL}/reset-password/{reset_token}", data={
        "csrf_token": csrf,
        "password": new_password,
        "confirm_password": new_password
    }, allow_redirects=False)
    print(f"Reset password status: {res.status_code}")
    
    print("9. Logging out...")
    res = session.get(f"{BASE_URL}/logout", allow_redirects=False)
    print(f"Logout status: {res.status_code}")
    
    print("10. Logging in with new password...")
    csrf = get_csrf(f"{BASE_URL}/login")
    res = session.post(f"{BASE_URL}/login", data={
        "csrf_token": csrf,
        "email": email,
        "password": new_password
    }, allow_redirects=False)
    print(f"New login status: {res.status_code}")
    if res.status_code == 302:
        print("✅ Logged in successfully with new password!")
    
    print("11. Testing WhatsApp Webhook (simulated)...")
    test_phone = f"+1555000{uid[:4]}"
    with psycopg.connect(DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO authorized_numbers (company_id, phone_number, name) VALUES (%s, %s, %s)",
                       (company_id, test_phone, "Test Phone"))
            conn.commit()
            
    res = requests.post(f"{BASE_URL}/webhook/whatsapp", data={
        "From": f"whatsapp:{test_phone}",
        "To": "whatsapp:+14155238886",
        "Body": "We poured 50 cubic yards of concrete on the west wing today. No safety issues."
    })
    print(f"Webhook status: {res.status_code}")
    if res.status_code == 200:
        print("✅ Webhook triggered successfully!")
    
    print("--- E2E Test Completed ---")

if __name__ == "__main__":
    run_tests()
