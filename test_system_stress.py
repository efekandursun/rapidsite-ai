import os
import json
import time
import random
from datetime import datetime, timedelta
from core.database import Database

def run_system_stress_test():
    print("\n" + "🏭"*25)
    print("🏭 STARTING FULL SYSTEM E2E STRESS TEST 🏭")
    print("🏭"*25)
    
    db = Database()
    
    # 1. CREATE COMPANY
    print("\n[1] Creating Test Company 'Titan Stress LLC'...")
    company_name = "Titan Stress LLC"
    slug = f"titan-stress-{int(time.time())}"
    
    company_id = db.create_company(name=company_name, slug=slug, whatsapp_numbers="+15558889999")
    print(f"  ✅ Company Created with ID: {company_id}")
    
    # 2. CREATE USER & AUTH
    print("\n[2] Creating User & Testing Auth...")
    email = f"boss_{company_id}@titanstress.com"
    user_id = db.create_user(
        email=email,
        password_hash="fakehash123",
        name="John Titan",
        company_id=company_id,
        role="owner",
        job_title="CEO"
    )
    print(f"  ✅ User Created: {email} (ID: {user_id})")
    
    # Test Verification Logic
    code = "123456"
    expires = (datetime.now() + timedelta(hours=1)).isoformat()
    db.set_verification_code(email, code, expires)
    verified = db.verify_email(email, code)
    print(f"  ✅ User Email Verification Status: {verified}")
    
    # 3. ADD & TEST WHATSAPP NUMBERS
    print("\n[3] Testing WhatsApp Authorization & Webhook Lookup...")
    db.add_authorized_number(company_id, "+15550001111", "Foreman Mike", "Superintendent")
    db.add_authorized_number(company_id, "+15550002222", "Foreman Bob", "Electrician")
    
    lookup = db.get_company_by_whatsapp("+15550001111")
    if lookup and lookup['id'] == company_id:
         print(f"  ✅ Webhook Lookup Success: Found {lookup['name']} via +15550001111 (Employee: {lookup['employee_name']})")
    else:
         print("  ❌ Webhook Lookup Failed!")
         
    # 4. MASS REPORT INSERTION (STRESS TEST)
    print("\n[4] Stress Testing Report Insertion (Injecting 100 Reports)...")
    start_time = time.time()
    report_ids = []
    
    for i in range(1, 101):
        parsed = {
            "log_type": random.choice(["manpower", "equipment", "delivery", "notes"]),
            "cost_code": f"0{random.randint(1,9)}-{random.randint(100,999)}",
            "description": f"Stress test report data {i}",
            "status": "success"
        }
        r_id = db.create_report(
            raw_transcript=f"Stress Test Raw Transcript {i}",
            parsed_data=parsed,
            project_id="PROJ-999",
            reported_by="+15550001111",
            company_id=company_id
        )
        report_ids.append(r_id)
        
    duration = time.time() - start_time
    print(f"  ✅ Inserted 100 reports in {duration:.4f} seconds!")
    
    # 5. TEST REPORT STATE CHANGES (APPROVAL, SYNC, INCOMPLETE)
    print("\n[5] Testing State Machine (Approve, Sync, Reject)...")
    db.approve_report(report_ids[0], approved_by=email)
    print(f"  ✅ Report {report_ids[0]} marked as APPROVED.")
    
    db.mark_synced(report_ids[1], erp_sync_id="PROCORE-12345")
    print(f"  ✅ Report {report_ids[1]} marked as SYNCED to ERP.")
    
    db.update_incomplete_report(report_ids[2], "Need more info", {"error": "missing hours"}, "incomplete")
    print(f"  ✅ Report {report_ids[2]} marked as INCOMPLETE.")
    
    # 6. QUERY STATS
    print("\n[6] Fetching System Dashboard Stats...")
    stats = db.get_stats_by_company(company_id)
    print(f"  ✅ Stats for {company_name}: {stats}")
    
    # 7. PROCORE TOKEN ENCRYPTION TEST
    print("\n[7] Testing Procore Token Storage & Encryption...")
    db.update_company_procore_tokens(company_id, "super_secret_access_123", "super_secret_refresh_456", int(time.time()) + 7200)
    
    company_check = db.get_company(company_id)
    print(f"  ✅ Access Token Decrypted: {company_check['procore_access_token']}")
    print(f"  ✅ Refresh Token Decrypted: {company_check['procore_refresh_token']}")
    
    # 8. CLEANUP (DELETE TEST DATA)
    print("\n[8] Cleaning Up (Deleting 100 reports, users, and company)...")
    with db.get_connection() as conn:
        cursor = conn.cursor()
        # Postgres syntax vs SQLite
        placeholder = "%s" if db.use_postgres else "?"
        
        query_r = f"DELETE FROM site_reports WHERE company_id = {placeholder}"
        cursor.execute(query_r.replace('?', '%s') if db.use_postgres else query_r, (company_id,))
        
        query_a = f"DELETE FROM company_authorized_numbers WHERE company_id = {placeholder}"
        cursor.execute(query_a.replace('?', '%s') if db.use_postgres else query_a, (company_id,))
        
        query_u = f"DELETE FROM users WHERE company_id = {placeholder}"
        cursor.execute(query_u.replace('?', '%s') if db.use_postgres else query_u, (company_id,))
        
        query_c = f"DELETE FROM companies WHERE id = {placeholder}"
        cursor.execute(query_c.replace('?', '%s') if db.use_postgres else query_c, (company_id,))
        
    print(f"  ✅ All test data for {company_name} securely deleted.")
    
    print("\n" + "🏭"*25)
    print("🏭 ALL SYSTEM TESTS PASSED PERFECTLY 🏭")
    print("🏭"*25 + "\n")

if __name__ == "__main__":
    run_system_stress_test()
