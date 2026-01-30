from django.core.management.base import BaseCommand

from api.views_extension import (
    check_for_crops,
    check_for_modify,
    check_for_unlabelled,
    ClipModel,
)
from api.qtservice.crop_application import start_crop_application
from api.qtservice.label_application import start_label_application
from api.qtservice.tag_application import start_tag_application
from api.qtservice.multitag_application import start_multitag_application
from api.qtservice.view_application import start_view_application
from api.qtservice.modify_application import start_modify_application
from api.qtservice.clip_application import start_clip_application
from api.qtservice.compare_application import start_compare_application

from functools import partial
from threading import Thread
from api.management.commands.watchdog_listener import (
    run_watchdog_listener,
    preprocess_watchdog_listener,
)
from api.utils.overrides import SERVICE_REQUIRED_TAGS


class Command(BaseCommand):
    def handle(self, **options):
        qtservice()


def qtservice():
    live_mode = True

    preprocess_watchdog_listener()

    Thread(target=run_watchdog_listener, daemon=True).start()

    command = ""
    while command != "exit":
        command = (
            input(
                "Enter command:\n1: Process media\n2: Tag application\n3: Compare application\n4: Viewer application\n+: "
            )
            .lower()
            .strip()
        )

        if command == "1":
            t = True
            idx = 0

            check_fns = (check_for_crops, check_for_modify, check_for_unlabelled)

            fns = [
                start_crop_application,
                start_modify_application,
                start_label_application,
                partial(start_multitag_application, SERVICE_REQUIRED_TAGS),
            ]

            while t and idx < len(fns):
                # Work through check functions
                for i in range(min(idx, len(check_fns))):
                    if check_fns[i]():
                        fns[i]()

                t, complete = fns[idx]()

                if not (idx == len(fns) - 1 and not complete):
                    idx += 1

            ClipModel.process_unclipped_items()

            if t:
                t, complete = start_clip_application()

            if t:
                t, complete = start_tag_application()

        if command == "1+":
            start_multitag_application()

        if command == "2":
            start_tag_application(tag_random=True)

        if command == "3":
            start_compare_application()

        if command == "4":
            start_view_application()

        print()

        if not live_mode:
            command = "exit"
