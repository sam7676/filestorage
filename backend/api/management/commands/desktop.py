from django.core.management.base import BaseCommand

from api.views_extension import (
    check_for_crops,
    check_for_modify,
    check_for_unlabelled,
    check_for_clips,
)
from api.desktop.crop_application import start_crop_application
from api.desktop.label_application import start_label_application
from api.desktop.tag_application import start_tag_application
from api.desktop.multitag_application import start_multitag_application
from api.desktop.view_application import start_view_application
from api.desktop.modify_application import start_modify_application
from api.desktop.clip_application import start_clip_application
from api.desktop.compare_application import start_compare_application

from functools import partial
from threading import Thread
from api.management.commands.watchdog_listener import (
    run_watchdog_listener,
    preprocess_watchdog_listener,
)
from api.utils.overrides import SERVICE_REQUIRED_TAGS


class Command(BaseCommand):
    def handle(self, **options):
        desktop()


def desktop():
    live_mode = True

    preprocess_watchdog_listener()

    Thread(target=run_watchdog_listener, daemon=True).start()

    command = ""
    while command != "exit":
        command = (
            input(
                "Enter command:\n1: Process media\n2: Compare application\n3: Viewer application\n+: "
            )
            .lower()
            .strip()
        )

        if command == "1":
            closed_automatically = True
            idx = 0

            check_fns = (
                check_for_crops,
                check_for_modify,
                check_for_unlabelled,
                check_for_clips,
            )

            fns = [
                start_crop_application,
                start_modify_application,
                start_label_application,
                start_clip_application,
                partial(start_multitag_application, SERVICE_REQUIRED_TAGS),
                start_tag_application,
            ]

            while closed_automatically and idx < len(fns):
                # Work through check functions
                for i in range(min(idx, len(check_fns))):
                    if check_fns[i]():
                        idx = i
                        break

                closed_automatically, completed_all_items = fns[idx]()

                idx += 1

        if command == "1m":
            start_multitag_application()

        if command == "1t":
            start_tag_application(tag_random=True)

        if command == "2":
            start_compare_application()

        if command == "3":
            start_view_application()

        print()

        if not live_mode:
            command = "exit"
