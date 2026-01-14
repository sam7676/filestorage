from dotenv import load_dotenv
import os

load_dotenv()

MEDIA_PATH = os.getenv("MEDIA_PATH")
DATABASE_PATH = os.getenv("DATABASE_PATH")
DROPBOX_PATH = os.getenv("DROPBOX_PATH")

CERT_PATH = os.getenv("CERT_PATH")
KEY_FILE_PATH = os.getenv("KEY_FILE_PATH")

UNPROCESSED_PATH = f"{MEDIA_PATH}/unprocessed"
ITEMS_PATH = f"{MEDIA_PATH}/items"

# Other paths are handled by a state map in models.py
