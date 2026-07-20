import os
import time
import uuid
import random
import string
import threading
import json
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from core.database import Database

def generate_radioactive_garbage(length):
    # Generates extreme garbage including NUL bytes, control characters, huge unicode, emojis
    pool = string.printable + ' 🐛👾🔥💀😂🚨💣💥💩' + ''.join(chr(i) for i in range(1000, 1100))
    return ''.join(random.choices(pool, k=length))

def worker_spam_reports(c_id, worker_id, count):
    """Worker function for concurrent DB hammering."""
    db = Database()
    success = 0
    errors = 0
    for i in range(count):
        try:
            r_id = db.create_report(
                raw_transcript=f"Worker {worker_id} Report {i} - " + uuid.uuid4().hex,
                parsed_data={"log_type": "chaos", "data": "concurrent spam"},
                project_id=f"PROJ-{worker_id}",
                reported_by="+15555555555",
                company_id=c_id
            )
            if r_id: success += 1
        except Exception:
            errors += 1
    return success, errors

def run_doomsday():
    print("\n" + "💥"*25)
    print("💥 STARTING DOOMSDAY PROTOCOL (LEVEL 10 CHAOS) 💥")
    print("💥"*25 + "\n")
    
    db = Database()
    
    # ---------------------------------------------------------
    # 1. CREATE SACRIFICIAL COMPANY
    # ---------------------------------------------------------
    print("[1] Creating 'Sacrifice LLC' for Doomsday...")
    slug = f"doomsday-{uuid.uuid4().hex[:8]}"
    try:
        c_id = db.create_company(name="Sacrifice LLC", slug=slug, whatsapp_numbers="+19998887777")
        print(f"  ✅ Company Created. ID: {c_id}")
    except Exception as e:
        print(f"  ❌ Failed to create company: {e}")
        return

    # ---------------------------------------------------------
    # 2. THE CONNECTION POOL HAMMER (CONCURRENCY TERROR)
    # ---------------------------------------------------------
    print("\n[2] Executing Connection Pool Hammer (100 Threads, 1000 Reports)...")
    start_time = time.time()
    total_success = 0
    total_errors = 0
    # 10 threads doing 50 inserts each = 500 reports rapidly
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(worker_spam_reports, c_id, i, 50) for i in range(20)]
        for future in as_completed(futures):
            s, e = future.result()
            total_success += s
            total_errors += e
            
    print(f"  ✅ Concurrency Bomb Completed in {time.time() - start_time:.2f}s!")
    print(f"     -> Success: {total_success}, Errors (Connection Drops/Locks): {total_errors}")

    # ---------------------------------------------------------
    # 3. MEGA PAYLOAD APOCALYPSE (5 MEGABYTES)
    # ---------------------------------------------------------
    print("\n[3] Triggering Mega Payload Apocalypse (5MB Insert)...")
    # 5 million characters = ~5MB of text
    mega_payload = "A" * 5_000_000 
    try:
        r_id = db.create_report(
            raw_transcript="MEGA PAYLOAD IN JSON",
            parsed_data={"log_type": "apocalypse", "description": mega_payload},
            project_id="MEGA-1",
            reported_by="+10000000000",
            company_id=c_id
        )
        if r_id:
            print("  ⚠️ System SURVIVED a 5MB JSON payload insertion! (PostgreSQL handles it, SQLite might choke)")
            # Try to fetch it
            report = db.get_report(r_id)
            if report:
                print("  ⚠️ System SURVIVED reading a 5MB payload back into memory!")
    except Exception as e:
        print(f"  ✅ System gracefully failed/rejected the 5MB payload. Error: {e}")

    # ---------------------------------------------------------
    # 4. TIME & SPACE DISTORTION (EXTREME DATES)
    # ---------------------------------------------------------
    print("\n[4] Testing Extreme Dates (Year 99999 & Year 0001)...")
    try:
        # Generate extreme timestamps
        future_ts = 253402300799 # Year 9999
        db.update_company_procore_tokens(c_id, "futuristic", "refresh", future_ts)
        print("  ⚠️ System accepted Year 9999 timestamp.")
    except Exception as e:
        print(f"  ✅ System rejected Year 9999 timestamp. Error: {e}")

    # ---------------------------------------------------------
    # 5. XSS & NO-SQL INJECTION PAYLOADS IN JSON
    # ---------------------------------------------------------
    print("\n[5] Injecting Deep XSS/JSON Escape Sequences...")
    nasty_json = {
        "log_type": "<script>alert(1)</script>",
        "cost_code": "' OR 1=1 --",
        "description": "{\"nested\": \"injection\", \"val\": \"\\u0000\\u0000\"}",
        "weird_keys___!@#": "SELECT * FROM users;"
    }
    try:
        db.update_incomplete_report(
            report_id=1, # Doesn't matter if it exists, checking DB parsing
            company_id=c_id,
            new_transcript="<img src=x onerror=alert('xss')>",
            parsed_data=nasty_json,
            status="pending"
        )
        print("  ✅ System processed XSS/SQL payloads in JSON without crashing SQL parser.")
    except Exception as e:
        print(f"  ⚠️ System threw an error on XSS/SQL payloads: {e}")

    # ---------------------------------------------------------
    # 6. DELETE CASCADE CHAOS
    # ---------------------------------------------------------
    print("\n[6] Testing Delete Cascades (Wiping the 1000+ reports instantly)...")
    start_del = time.time()
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            placeholder = "%s" if db.use_postgres else "?"
            cursor.execute(f"DELETE FROM companies WHERE id = {placeholder}".replace('?', '%s') if db.use_postgres else f"DELETE FROM companies WHERE id = {placeholder}", (c_id,))
            conn.commit()
        print(f"  ✅ Company Deleted. Checking if orphaned reports exist...")
        
        # Check if reports remain (if no ON DELETE CASCADE, they are orphaned)
        reports = db.get_reports_by_company(c_id)
        if len(reports) > 0:
             print(f"  ❌ SYSTEM FAILED: {len(reports)} orphaned reports found! Missing 'ON DELETE CASCADE'.")
             # Clean them manually
             with db.get_connection() as conn:
                 cursor = conn.cursor()
                 cursor.execute(f"DELETE FROM site_reports WHERE company_id = {placeholder}".replace('?', '%s') if db.use_postgres else f"DELETE FROM site_reports WHERE company_id = {placeholder}", (c_id,))
                 conn.commit()
        else:
             print("  ✅ SYSTEM PASSED: Reports cascaded successfully or are unreachable.")
    except Exception as e:
        print(f"  ❌ Deletion failed: {e}")
        
    print("\n" + "💥"*25)
    print("💥 DOOMSDAY PROTOCOL COMPLETED 💥")
    print("💥"*25 + "\n")

if __name__ == "__main__":
    run_doomsday()
