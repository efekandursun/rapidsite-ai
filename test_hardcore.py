import os
import json
from dotenv import load_dotenv
from core.database import Database
from core.brain import ConstructionBrain

load_dotenv()

def run_hardcore_tests():
    db = Database()
    brain = ConstructionBrain()
    
    print("\n" + "🔥"*25)
    print("🔥 STARTING HARDCORE AI LIMIT TESTS 🔥")
    print("🔥"*25)
    
    company = db.get_company(1)
    if not company:
        print("❌ No company found in DB.")
        return
        
    print(f"✅ Testing AI for Company: {company['name']}\n")
    
    # =========================================================================
    # TEST 1: THE "EVERYTHING IS A MESS" (Slang + Mixed Languages + Ranting)
    # =========================================================================
    print("🧪 TEST 1: The 'Drunk Foreman' Scenario (Mixed language & ranting)")
    msg1 = "Abi bu ne ya, the weather is absolute garbage today raining cats and dogs. Adamlar from Apex sabahtan beri 5 saat yattı sonra only 2 guys worked for 3 hours on framing. Bu arada o kiraladığımız John Deere traktör var ya, completely busted, 0 hours operated, sat idle for 8 hours. Anyway, gidiyorum ben."
    print(f"📥 INPUT:\n{msg1}")
    
    try:
        parsed1 = brain.parse_text(msg1, company)
        print("\n📤 OUTPUT:")
        for event in parsed1:
            print(f" - [{event['log_type'].upper()}] | Item: {event.get('item', '')} | Desc: {event.get('description', '')}")
            if event['log_type'] == 'equipment':
                print(f"    -> EQ Status: OP {event['equipment_details'].get('hours_operating')}h | IDLE {event['equipment_details'].get('hours_idle')}h")
            if event['log_type'] == 'manpower':
                print(f"    -> MP Status: {event['crew'].get('count')} guys, {event['crew'].get('hours')} hours")
    except Exception as e:
        print(f"❌ Failed: {e}")

    # =========================================================================
    # TEST 2: THE "TOTAL CONTRADICTION" (Changing mind 3 times)
    # =========================================================================
    print("\n" + "-"*50)
    print("🧪 TEST 2: The 'Contradiction' Scenario (Changing mind mid-sentence)")
    msg2 = "We received a delivery from Home Depot. It was 50 bags of cement. Wait, no, not cement, it was drywall. Yeah, 50 sheets of drywall. Actually, scratch that entire thing, it wasn't Home Depot, it was Lowe's, and they delivered exactly 120 pieces of 2x4 lumber."
    print(f"📥 INPUT:\n{msg2}")
    
    try:
        parsed2 = brain.parse_text(msg2, company)
        print("\n📤 OUTPUT:")
        for event in parsed2:
            print(f" - [{event['log_type'].upper()}] | Vendor: {event['delivery_details'].get('delivery_from', '')} | Item: {event.get('item', '')} | Qty: {event.get('quantity', '')}")
    except Exception as e:
        print(f"❌ Failed: {e}")

    # =========================================================================
    # TEST 3: THE "MASSIVE BATCH" (6 different logs in one breath)
    # =========================================================================
    print("\n" + "-"*50)
    print("🧪 TEST 3: The 'Massive Batch' Scenario (6 events in one message)")
    msg3 = "Daily update for Building C: 10 guys from Titan Plumbing worked 8 hours. We had a safety incident where a guy tripped over a wire, but he's fine. A health inspector came by and everything was approved. The big crane was operating for 10 hours straight. Also we took delivery of 5 tons of steel from CMC. Oh and somebody left a note that the main gate lock is broken, need to fix that tomorrow."
    print(f"📥 INPUT:\n{msg3}")
    
    try:
        parsed3 = brain.parse_text(msg3, company)
        print("\n📤 OUTPUT:")
        print(f"Total events extracted: {len(parsed3)}")
        for event in parsed3:
            print(f" - [{event['log_type'].upper()}] -> {event.get('description', '')[:60]}...")
    except Exception as e:
        print(f"❌ Failed: {e}")

    # =========================================================================
    # TEST 4: THE "PASSIVE AGGRESSIVE ZERO INFO" (Testing Follow-ups)
    # =========================================================================
    print("\n" + "-"*50)
    print("🧪 TEST 4: The 'Passive Aggressive' Scenario (Refusing to elaborate)")
    msg4 = "There was an accident."
    print(f"📥 INPUT 1: {msg4}")
    
    try:
        parsed4 = brain.parse_text(msg4, company)
        print(f"📤 OUTPUT 1: Status = {parsed4[0]['status']}")
        print(f"❓ AI Asked: {parsed4[0].get('follow_up_question')}")
        
        msg4_followup = "I don't want to talk about it."
        print(f"\n📥 INPUT 2 (Follow up): {msg4_followup}")
        
        resolution = brain.resolve_incomplete(parsed4[0], msg4_followup, company)
        updated = resolution.get('updated_incomplete_event', {})
        print(f"📤 OUTPUT 2: Status = {updated.get('status')}")
        print(f"📝 Final Description Saved: {updated.get('description')}")
    except Exception as e:
        print(f"❌ Failed: {e}")

    print("\n" + "🔥"*25)
    print("🔥 HARDCORE TESTS COMPLETED 🔥")
    print("🔥"*25 + "\n")

if __name__ == "__main__":
    run_hardcore_tests()
