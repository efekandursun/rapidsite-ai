import os
import json
import time
from dotenv import load_dotenv
from core.database import Database
from core.brain import ConstructionBrain
from app import sync_report_to_procore

load_dotenv()

def run_tests():
    db = Database()
    brain = ConstructionBrain()
    
    print("\n" + "="*50)
    print("🚀 STARTING FULL E2E SYSTEM AUDIT & TEST")
    print("="*50)
    
    # Get active company (assuming ID 1 for test environment)
    company = db.get_company(1)
    if not company:
        print("❌ Error: No company found in local DB. Tests aborted.")
        return
        
    print(f"✅ Loaded Company: {company['name']}")
    
    success_count = 0
    total_tests = 3
    
    # ---------------------------------------------------------
    # TEST 1: Complex Multi-Event & Self-Correction Parsing
    # ---------------------------------------------------------
    print("\n--- TEST 1: Complex Multi-Event Parsing ---")
    msg1 = "Hey boss, 4 guys from Apex worked for 10 hours today on plumbing. Also, the CAT excavator sat idle for 3 hours, no wait, it operated for 5 hours and was idle for 1 hour. Oh, and Home Depot delivered 50 bags of cement."
    print(f"INPUT: {msg1}")
    
    try:
        parsed1 = brain.parse_text(msg1, company)
        if len(parsed1) == 3:
            print("✅ Successfully parsed into 3 distinct events.")
            
            # Verify Equipment correction
            eq_event = next((e for e in parsed1 if e['log_type'] == 'equipment'), None)
            if eq_event and eq_event['equipment_details']['hours_operating'] == 5 and eq_event['equipment_details']['hours_idle'] == 1:
                print("✅ Successfully handled mid-sentence correction (5 op / 1 idle).")
                success_count += 1
            else:
                print(f"❌ Failed to parse equipment correction properly: {json.dumps(eq_event, indent=2)}")
        else:
            print(f"❌ Expected 3 events, got {len(parsed1)}")
    except Exception as e:
        print(f"❌ Exception in Test 1: {e}")

    # ---------------------------------------------------------
    # TEST 2: Incomplete Resolution & "I don't know" Feature
    # ---------------------------------------------------------
    print("\n--- TEST 2: Incomplete Report & 'Skip' Handling ---")
    msg2 = "We received a delivery of steel beams today at building B."
    print(f"INPUT: {msg2}")
    
    try:
        parsed2 = brain.parse_text(msg2, company)
        if len(parsed2) == 1 and parsed2[0]['status'] == 'incomplete':
            print("✅ Successfully identified missing info (Quantity).")
            
            # Follow up with "I don't know"
            follow_up = "I don't know the exact quantity, just skip it."
            print(f"FOLLOW UP: {follow_up}")
            
            resolution = brain.resolve_incomplete(parsed2[0], follow_up, company)
            
            if resolution.get('updated_incomplete_event', {}).get('status') == 'complete':
                print("✅ Successfully handled 'Skip' / 'I don't know' command and marked as complete.")
                success_count += 1
            else:
                print(f"❌ Failed to mark as complete on skip: {json.dumps(resolution, indent=2)}")
        else:
            print(f"❌ Failed to mark initial message as incomplete: {json.dumps(parsed2, indent=2)}")
    except Exception as e:
        print(f"❌ Exception in Test 2: {e}")

    # ---------------------------------------------------------
    # TEST 3: End-to-End Procore Sync
    # ---------------------------------------------------------
    print("\n--- TEST 3: Procore Sync (E2E) ---")
    if not company.get('procore_access_token'):
        print("⚠️ Skipping Test 3: No Procore access token found for this company.")
        total_tests -= 1
    else:
        try:
            # Let's insert the Manpower event from Test 1 into the DB
            mp_event = next((e for e in parsed1 if e['log_type'] == 'manpower'), None)
            
            with db.get_connection() as conn:
                cursor = db._execute(conn, """
                    INSERT INTO site_reports (company_id, raw_transcript, parsed_data, log_type, status)
                    VALUES (?, ?, ?, ?, 'approved')
                    RETURNING id
                """, (company['id'], "Test Manpower", json.dumps(mp_event), "manpower"))
                report_id = cursor.fetchone()[0]
                
            print(f"Created Approved Test Report ID: #{report_id}")
            
            # Fetch the inserted report
            report = db.get_report(report_id)
            
            # Attempt Sync
            print("Attempting to sync to Procore...")
            success, message = sync_report_to_procore(report)
            
            if success:
                print(f"✅ Procore Sync Successful! Response: {message}")
                success_count += 1
            else:
                print(f"❌ Procore Sync Failed: {message}")
                
            # Cleanup DB
            with db.get_connection() as conn:
                db._execute(conn, "DELETE FROM site_reports WHERE id=?", (report_id,))
                
        except Exception as e:
            print(f"❌ Exception in Test 3: {e}")

    # ---------------------------------------------------------
    # SUMMARY
    # ---------------------------------------------------------
    print("\n" + "="*50)
    print(f"📊 TEST SUITE SUMMARY: {success_count}/{total_tests} SUCCESS")
    print(f"🎯 SUCCESS RATE: {(success_count/total_tests)*100:.1f}%")
    print("="*50)

if __name__ == "__main__":
    run_tests()
