from django.contrib.auth.models import User
import sys
from manage import main as manage_main
from django.core.management.base import BaseCommand
import hashlib


def hash_password(password: bytes) -> str:
    salt = b"helloworld"
    iterations = 1000
    keylen = 64
    digest = "sha512"

    dk = hashlib.pbkdf2_hmac(digest, password, salt, iterations, dklen=keylen)

    return dk.hex()


class Command(BaseCommand):
    def handle(self, **options):
        sys.argv = ["manage.py", "migrate"]

        manage_main()

        sys.argv = ["manage.py", "makemigrations"]

        manage_main()

        username = input("Enter username: ")
        password = input("Enter password: ")
        password = hash_password(password.encode("utf-8"))

        User.objects.create_user(username=username, password=password)
