import sys
import os
import random
from datetime import datetime

# Add the project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import Database

def seed_db():
    db = Database()
    
    # Get user / company
    user = db.get_user_by_email("efekan@fieldflow.ai") or db.get_user_by_whatsapp("+905464055467")
    if not user:
        print("User not found!")
        company_id = 1
        phone = "+905464055467"
    else:
        company_id = user['company_id']
        phone = user['whatsapp_number'] or "+905464055467"
        
    print(f"Using Company ID: {company_id}, Phone: {phone}")
    
    reports = [
        {
            "log_type": "manpower",
            "raw": "Bugün B Blok 2. katta alçıpan ustası olarak çalışan 4 kişi 8 saat mesai yaptı.",
            "translated": "Today, 4 people working as drywall masters on the 2nd floor of Block B worked 8 hours.",
            "parsed": {
                "company": "Drywall Masters Inc",
                "workers": 4,
                "hours": 8,
                "location": "Block B > Level 2",
                "comments": "Completed standard daily tasks."
            }
        },
        {
            "log_type": "equipment",
            "raw": "Ekskavatör bugün 6 saat çalıştı, 2 saat boşta bekledi.",
            "translated": "The excavator operated for 6 hours today and was idle for 2 hours.",
            "parsed": {
                "equipment_name": "Excavator",
                "hours_operating": 6,
                "hours_idle": 2,
                "location": "Site A",
                "comments": "Routine earthmoving operations."
            }
        },
        {
            "log_type": "quantity",
            "raw": "Bugün 500 metrekare fayans döşendi.",
            "translated": "500 square meters of tiles were laid today.",
            "parsed": {
                "material": "Ceramic Tiles",
                "quantity": 500,
                "unit": "sqm",
                "location": "Lobby",
                "comments": "Finished the main lobby floor."
            }
        },
        {
            "log_type": "safety",
            "raw": "Bir işçi baretsiz sahaya girdi, hemen uyarıldı ve baret taktırıldı.",
            "translated": "A worker entered the site without a hard hat, was immediately warned and made to wear one.",
            "parsed": {
                "incident_type": "PPE Violation",
                "severity": "Low",
                "location": "Gate C",
                "description": "Worker without hard hat.",
                "action_taken": "Verbal warning and PPE provided."
            }
        },
        {
            "log_type": "delivery",
            "raw": "10 ton çimento şantiyeye ulaştı.",
            "translated": "10 tons of cement arrived at the site.",
            "parsed": {
                "material": "Cement",
                "quantity": 10,
                "unit": "tons",
                "supplier": "CemCorp",
                "comments": "Unloaded at storage area 2."
            }
        },
        {
            "log_type": "dumpster",
            "raw": "Öğleden önce sahaya 2 adet boş çöp konteyneri getirildi, dolan 1 adet konteyner ise götürüldü.",
            "translated": "2 empty dumpsters were brought to the site before noon, and 1 full dumpster was taken away.",
            "parsed": {
                "company": "Waste Management Co",
                "action": "Delivered and Removed",
                "delivered_qty": 2,
                "removed_qty": 1,
                "comments": "Routine waste removal."
            }
        },
        {
            "log_type": "weather",
            "raw": "Sabah yoğun yağmur vardı, öğleden sonra güneş açtı. Sıcaklık 15 dereceydi.",
            "translated": "There was heavy rain in the morning, the sun came out in the afternoon. The temperature was 15 degrees.",
            "parsed": {
                "condition": "Rainy to Sunny",
                "temperature": "15°C",
                "impact": "Delayed exterior painting by 2 hours."
            }
        },
        {
            "log_type": "visitors",
            "raw": "Belediye müfettişleri öğleden sonra 2 saatliğine sahayı gezdi.",
            "translated": "Municipal inspectors toured the site for 2 hours in the afternoon.",
            "parsed": {
                "visitor_name": "Municipal Inspectors",
                "purpose": "Routine Check",
                "duration_hours": 2,
                "comments": "No major issues found."
            }
        },
        {
            "log_type": "inspections",
            "raw": "Kalite kontrol ekibi beton dökümünü inceledi ve onay verdi.",
            "translated": "The QC team inspected the concrete pouring and gave approval.",
            "parsed": {
                "inspection_type": "Concrete Pouring QC",
                "status": "Approved",
                "inspector": "QC Team Alpha",
                "comments": "Slump test passed."
            }
        },
        {
            "log_type": "productivity",
            "raw": "Duvar ekibi bugün planlananın %20 ilerisine geçti.",
            "translated": "The wall team got 20% ahead of schedule today.",
            "parsed": {
                "crew": "Wall Team",
                "progress": "20% Ahead",
                "comments": "Excellent performance today."
            }
        },
        {
            "log_type": "timecards",
            "raw": "Ahmet Yılmaz bugün 8 saat çalıştı.",
            "translated": "Ahmet Yilmaz worked 8 hours today.",
            "parsed": {
                "employee": "Ahmet Yilmaz",
                "hours": 8,
                "cost_code": "03-100 Concrete",
                "billable": True
            }
        },
        {
            "log_type": "notes",
            "raw": "Yarın elektrik kesintisi olacak, jeneratörleri hazırlayalım.",
            "translated": "There will be a power outage tomorrow, let's prepare the generators.",
            "parsed": {
                "subject": "Power Outage Warning",
                "description": "Prepare generators for tomorrow's power cut.",
                "action_required": True
            }
        },
        {
            "log_type": "delays",
            "raw": "Vinç arızası yüzünden çelik montajı 3 saat gecikti.",
            "translated": "Steel erection was delayed by 3 hours due to a crane malfunction.",
            "parsed": {
                "cause": "Crane Malfunction",
                "impact": "Steel Erection",
                "delay_hours": 3,
                "comments": "Maintenance team notified."
            }
        }
    ]
    
    print(f"Seeding {len(reports)} mock reports...")
    
    # Set everything to pending so the manager can approve/reject them.
    for r in reports:
        r['parsed']['log_type'] = r['log_type']
        
        report_id = db.create_report(
            raw_transcript=r['raw'],
            parsed_data=r['parsed'],
            project_id=None,
            reported_by=phone,
            company_id=company_id,
            media_paths=None
        )
        
        status = 'pending'
        with db.get_connection() as conn:
            db._execute(conn, "UPDATE site_reports SET status = %s WHERE id = %s", (status, report_id))
            
        print(f"Created {r['log_type']} report with ID {report_id} ({status}).")
        
    print("Seeding complete!")

if __name__ == '__main__':
    seed_db()
