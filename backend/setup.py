import os

required_env_variables = """
MEDIA_PATH=
DATABASE_PATH=
DROPBOX_PATH=
CERT_PATH='selftest_cert'
KEY_FILE_PATH='selftest_key'
DJANGO_SECRET_KEY='delete_this_insecure_key'
"""

backend_env_path = ".env"
if not os.path.exists(backend_env_path):
    with open(backend_env_path, "w") as f:
        lines = required_env_variables.split("\n")
        lines = [line.strip() + "\n" for line in lines if line.strip()]

        f.writelines(lines)

override_code = """
from api.views_extension import TagConditions

def override_random_item(tags, filetype):
    return tags

def get_view_default_tags():
    return {
            ("state", "needsclip"): TagConditions.Is.value,
            ("state", "needstags"): TagConditions.Is.value,
            ("state", "complete"): TagConditions.Is.value,
            ("_", "_"): TagConditions.Is.value,
        }

SERVICE_REQUIRED_TAGS = ()

PRIORITY_TAG_MAP = {}
PRIORITY_COLORS = {}
"""
override_path = "api/utils/overrides.py"
if not os.path.exists(override_path):
    with open(override_path, "w") as f:
        lines = override_code.split("\n")
        lines = [line + "\n" for line in lines if line.strip()]

        f.writelines(lines)
