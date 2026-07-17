from core.database import Database
print("Starting")
db = Database()
print("Getting pool")
pool = db._get_pool()
print("Pool:", pool)
