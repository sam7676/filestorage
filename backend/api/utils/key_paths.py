from dotenv import load_dotenv
import os

load_dotenv()

MEDIA_PATH = os.getenv("MEDIA_PATH")
DATABASE_PATH = os.getenv("DATABASE_PATH")


def _split_paths(value):
    if not value:
        return []
    return [path.strip() for path in value.split(os.pathsep) if path.strip()]


READER_PATHS = _split_paths(os.getenv("READER_PATHS"))

CERT_PATH = os.getenv("CERT_PATH")
KEY_FILE_PATH = os.getenv("KEY_FILE_PATH")

UNPROCESSED_PATH = f"{MEDIA_PATH}/unprocessed"
ITEMS_PATH = f"{MEDIA_PATH}/items"

# Other paths are handled by a state map in models.py
