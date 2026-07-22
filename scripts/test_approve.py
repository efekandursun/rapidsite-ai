import sys
sys.path.append('.')
from core.database import Database
from core.whatsapp_handler import process_text_message
import json

db = Database()

# Wipe DB
with db.get_connection() as conn:
    db._execute(conn, "DELETE FROM site_reports")

# Send a message
print("1. Sending message")
process_text_message('Bugün 2 işçi 3 saat çalıştı', None, '+905464055467', [])

# Verify DB
print("\n2. DB state after message:")
for r in db.get_all_pending_reports_for_user('+905464055467'):
    print(f"ID {r['id']}: {r['parsed_data']}")

# Approve
print("\n3. Approving")
process_text_message('1', None, '+905464055467', [])

# Verify DB
print("\n4. DB state after approve:")
for r in db.get_all_pending_reports_for_user('+905464055467'):
    print(f"ID {r['id']}: {r['parsed_data']}")

