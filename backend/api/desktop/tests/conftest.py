import os


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "filestoragebackend.settings")

try:
    import django

    django.setup()
except Exception:
    pass
