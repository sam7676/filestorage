from django_extensions.management.commands.runserver_plus import (
    Command as RunserverPlusCommand,
)
from api.management.commands.watchdog_listener import preprocess_watchdog_listener
from api.utils.key_paths import READER_PATHS, CERT_PATH, KEY_FILE_PATH


class Command(RunserverPlusCommand):
    started = False

    def inner_run(self, *args, **options):
        args[0]["cert_path"] = CERT_PATH
        args[0]["key_file_path"] = KEY_FILE_PATH
        args[0]["use_reloader"] = False

        if not Command.started:
            Command.started = True

            # Does nothing if path does not exist
            preprocess_watchdog_listener(
                READER_PATHS,
            )

        return super().inner_run(*args, **options)
