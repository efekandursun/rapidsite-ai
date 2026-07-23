import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.database import Database

def reset():
    db = Database()
    with db.get_connection() as conn:
        db._execute(conn, "DELETE FROM site_reports")
        print("Cleared all site reports.")

if __name__ == "__main__":
    reset()
