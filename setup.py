import os

os.makedirs("data", exist_ok=True)
db_path = "data/database.sqlite3"
if not os.path.exists(db_path):
    open(db_path, "a").close()
