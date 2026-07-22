import sys
sys.path.append('.')
from core.database import Database
db = Database()
r = db.get_latest_pending_report_for_user('+905464055467')
if r:
    print("TYPE OF PARSED DATA:", type(r['parsed_data']))
