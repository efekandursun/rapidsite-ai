from core.database import Database
db = Database()
if hasattr(db, '_init_schema'):
    db._init_schema()
    print("Schema initialized.")
else:
    print("No _init_schema method found.")
