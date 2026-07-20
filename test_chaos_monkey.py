import os
import time
import uuid
import random
import string
from datetime import datetime, timedelta
from core.database import Database

def generate_garbage(length=5000):
    return ''.join(random.choices(string.ascii_letters + string.digits + string.punctuation + ' 🐛👾🔥💀😂', k=length))

def run_chaos_monkey():
    print("\n" + "🐒"*25)
    print("🐒 STARTING SYSTEM CHAOS MONKEY TESTS 🐒")
    print("🐒 (Extreme Boundary, Isolation & Integrity Tests) 🐒")
    print("🐒"*25 + "\n")
    
    db = Database()
    
    # ---------------------------------------------------------
    # 1. THE SQL INJECTION & CRAZY UNICODE ATTEMPT
    # ---------------------------------------------------------
    print("[1] Testing SQL Injection & Unicode Resilience on Company Creation...")
    nasty_string = "'; DROP TABLE companies; -- 😈 / NULL \x00 \n \r \t 🦧"
    slug = f"chaos-slug-{uuid.uuid4().hex[:8]}"
    try:
        c_id = db.create_company(name=nasty_string, slug=slug, whatsapp_numbers="+19999999999")
        if c_id:
            company = db.get_company(c_id)
            if company and company['name'] == nasty_string:
                print("  ✅ Passed: System successfully handled nasty injection string without crashing or executing it.")
            else:
                print("  ❌ Failed: Data was mangled on insert.")
        else:
            print("  ❌ Failed to create company with nasty string.")
    except Exception as e:
        print(f"  ❌ Failed with Exception: {e}")
        c_id = None
        # We don't return here so the other tests can still run!
        
        # We need a c_id for the rest of the tests to work, so let's create a normal company if it failed.
        if c_id is None:
            c_id = db.create_company(name="Chaos Fallback", slug=f"fallback-{uuid.uuid4().hex[:8]}")

    # ---------------------------------------------------------
    # 2. THE MASSIVE PAYLOAD TEST
    # ---------------------------------------------------------
    print("\n[2] Testing Massive Data Payload on Reports...")
    huge_data = generate_garbage(50000) # 50k chars
    huge_parsed = {"log_type": "notes", "description": huge_data}
    try:
        r_id = db.create_report(
            raw_transcript=huge_data,
            parsed_data=huge_parsed,
            project_id="CHAOS-101",
            reported_by="+19999999999",
            company_id=c_id
        )
        if r_id:
            report = db.get_report(r_id)
            if report and len(report['raw_transcript']) == 50000:
                print("  ✅ Passed: System successfully saved and retrieved a massive 50,000 char payload.")
            else:
                print("  ❌ Failed: Huge payload was truncated or missing.")
        else:
            print("  ❌ Failed to insert massive report.")
    except Exception as e:
        print(f"  ❌ Failed with Exception: {e}")

    # ---------------------------------------------------------
    # 3. THE DUPLICATE SLUG/EMAIL INTEGRITY TEST
    # ---------------------------------------------------------
    print("\n[3] Testing Unique Constraints (Duplicate Slugs & Emails)...")
    try:
        # Should raise an IntegrityError or similar
        db.create_company(name="Duplicate", slug=slug) # same slug
        print("  ❌ Failed: System ALLOWED duplicate company slug!")
    except Exception as e:
        print("  ✅ Passed: System blocked duplicate company slug as expected.")

    email = f"chaos_{uuid.uuid4().hex[:6]}@monkey.com"
    u_id = db.create_user(email=email, password_hash="hash", name="Monkey", company_id=c_id, role="admin", job_title="Chaos")
    try:
        db.create_user(email=email, password_hash="hash2", name="Monkey 2", company_id=c_id, role="user", job_title="Chaos 2")
        print("  ❌ Failed: System ALLOWED duplicate user email!")
    except Exception as e:
        print("  ✅ Passed: System blocked duplicate user email as expected.")

    # ---------------------------------------------------------
    # 4. TENANT ISOLATION (CROSS-COMPANY APPROVAL ATTEMPT)
    # ---------------------------------------------------------
    print("\n[4] Testing Tenant Isolation (Cross-Company Access)...")
    try:
        # Create second company
        slug2 = f"victim-slug-{uuid.uuid4().hex[:8]}"
        victim_c_id = db.create_company(name="Victim LLC", slug=slug2)
        
        # Create report in victim company
        vic_r_id = db.create_report(
            raw_transcript="Normal report",
            parsed_data={"log_type": "notes", "description": "test"},
            project_id="VIC-1",
            reported_by="+18888888888",
            company_id=victim_c_id
        )
        
        # Now let's see if our DB methods enforce anything (they might not at the DB layer, 
        # but let's test if we can approve it by just supplying the ID).
        # typically tenant isolation is done in the app layer, but let's check DB behavior.
        res = db.approve_report(vic_r_id, c_id, approved_by=email) 
        # email belongs to c_id. The DB approve_report might just accept any string.
        # Let's check if the app handles this in the app layer. 
        if res:
             print("  ⚠️ Warning: DB layer allows cross-company approval (expected if tenant isolation is in App layer).")
        else:
             print("  ✅ DB layer blocked cross-company approval.")
    except Exception as e:
        print(f"  ❌ DB Layer exception on cross company: {e}")

    # ---------------------------------------------------------
    # 5. GHOST UPDATES (UPDATING NON-EXISTENT RECORDS)
    # ---------------------------------------------------------
    print("\n[5] Testing Ghost Updates (Modifying non-existent entities)...")
    try:
        res = db.approve_report(999999999, c_id, approved_by="ghost@ghost.com")
        if not res:
            print("  ✅ Passed: Gracefully handled updating a non-existent report (returned False/None).")
        else:
            print("  ❌ Failed: Update returned success for a non-existent report!")
            
        res2 = db.update_company_procore_tokens(999999999, "token", "refresh", 123456)
        if not res2:
             print("  ✅ Passed: Gracefully handled updating tokens for non-existent company.")
        else:
             print("  ❌ Failed: Update returned success for non-existent company tokens!")
    except Exception as e:
        print(f"  ❌ Failed with Exception: {e}")

    # ---------------------------------------------------------
    # 6. TIME TRAVELLER (EXPIRED TOKENS & DATES)
    # ---------------------------------------------------------
    print("\n[6] Testing Expired Tokens & Time Travel...")
    past_time = int(time.time()) - 100000
    try:
        db.update_company_procore_tokens(c_id, "past_access", "past_refresh", past_time)
        comp_check = db.get_company(c_id)
        if comp_check['procore_expires_at'] == past_time:
             print("  ✅ Passed: Allowed storing past timestamps (App layer should handle expiration logic).")
        else:
             print("  ❌ Failed to store past timestamp.")
    except Exception as e:
        print(f"  ❌ Failed with Exception: {e}")

    # ---------------------------------------------------------
    # 7. CLEANUP
    # ---------------------------------------------------------
    print("\n[7] Chaos Monkey Cleanup...")
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            placeholder = "%s" if db.use_postgres else "?"
            
            # Delete victim company and its reports
            query_r = f"DELETE FROM site_reports WHERE company_id = {placeholder}"
            cursor.execute(query_r.replace('?', '%s') if db.use_postgres else query_r, (victim_c_id,))
            query_c = f"DELETE FROM companies WHERE id = {placeholder}"
            cursor.execute(query_c.replace('?', '%s') if db.use_postgres else query_c, (victim_c_id,))
            
            # Delete chaos company and its reports/users
            cursor.execute(query_r.replace('?', '%s') if db.use_postgres else query_r, (c_id,))
            query_u = f"DELETE FROM users WHERE company_id = {placeholder}"
            cursor.execute(query_u.replace('?', '%s') if db.use_postgres else query_u, (c_id,))
            cursor.execute(query_c.replace('?', '%s') if db.use_postgres else query_c, (c_id,))
            
        print("  ✅ Passed: All chaos data destroyed successfully.")
    except Exception as e:
        print(f"  ❌ Cleanup Failed: {e}")
        
    print("\n" + "🐒"*25)
    print("🐒 CHAOS MONKEY TESTS COMPLETED 🐒")
    print("🐒"*25 + "\n")

if __name__ == "__main__":
    run_chaos_monkey()
