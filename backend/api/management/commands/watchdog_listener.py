import time
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer
from heapq import heappush, heappop
from collections import defaultdict
from math import floor
import os
from api.models import (
    get_file_properties,
    try_get_item,
    FileState,
)
from api.utils.key_paths import MEDIA_PATH, READER_PATHS
from threading import Lock
from api.views_extension import edit_item, get_dimensions, upload_item, VideoRemover
from api.management.commands.cleandb import clean_db


PROCESS_TIME = 5  # How often we process new watchdog updates
DELETED_SCALE = (
    3  # How many process time cycles between checking a deleted item's final state
)


class EventProcessor:
    banned_filetypes = (
        ".TMP",
        ".ini",
    )

    def __init__(self):
        self.process_times = []  # heap of process times to process
        self.unique_process_times = (
            set()
        )  # set of process times (ensuring heap is unique)
        self.file_assignments = defaultdict(int)
        self.time_assignments = defaultdict(set)
        self.lock = Lock()

    def process(self):
        with self.lock:
            seconds = floor(time.time())
            ready_to_process = True

            while self.process_times and ready_to_process:
                # Checks if any items are ready to be processed
                latest_seconds = self.process_times[0]
                ready_to_process = seconds >= latest_seconds

                if not ready_to_process:
                    continue

                # Processes all data with a time associated with latest_seconds
                for file_data in self.time_assignments[latest_seconds]:
                    path, event_type = file_data

                    # File has been processed, ignore
                    self.file_assignments.pop(file_data)

                    self.check_path(path, event_type)

                self.time_assignments.pop(latest_seconds)
                self.unique_process_times.remove(latest_seconds)
                heappop(self.process_times)

    def add(self, path, event_type):
        if any(banned_ft in path for banned_ft in self.banned_filetypes):
            return

        with self.lock:
            file_data = (path, event_type)

            # Declaring how many seconds until we inspect the file

            timestamp = (
                floor(time.time()) + PROCESS_TIME * DELETED_SCALE
                if event_type == "deleted"
                else floor(time.time()) + PROCESS_TIME
            )

            # Remove prior file information

            if file_data in self.file_assignments:
                remove_time = self.file_assignments[file_data]
                self.time_assignments[remove_time].remove(file_data)

            self.file_assignments[file_data] = timestamp
            self.time_assignments[timestamp].add(file_data)

            # If the timestamp is new, add it to the heap to inspect
            if timestamp not in self.unique_process_times:
                self.unique_process_times.add(timestamp)
                heappush(self.process_times, timestamp)

    def check_path(self, path, event_type):
        # We have the latest version of the file. We are now looking to update it in our database.

        if event_type == "deleted":
            self.handle_delete(path)
        else:
            self.handle_check(path)

    @staticmethod
    def handle_check(path, compare_edits=True):
        if not os.path.exists(path):
            return

        item, properties = try_get_item(path)

        if item:
            expected_path = item.getpath()

            # Item is in database as expected, move on
            if expected_path == path:
                return

            expected_properties = get_file_properties(expected_path)

            label = properties["label"]
            category = properties["category"]
            expected_category = expected_properties["category"]

            # The category is correct, but the labels are different. This usually means we've just changed the label and that's all that's mismatching.
            # Tags will still be valid.
            if label != item.label and category == expected_category:
                edit_item(item_id=item.id, new_label=label, new_state=item.state)
                return

            # If the expected category is different (we've moved to a different processing stage), we edit our item again
            elif category != expected_category:
                state_map = {
                    "items": FileState.NeedsClip,
                    "uncropped": FileState.NeedsCrop,
                    "needsmodify": FileState.NeedsModify,
                    "unlabelled": FileState.NeedsLabel,
                }

                edit_item(
                    item_id=item.id, new_label=label, new_state=state_map[category]
                )
                return

            elif compare_edits:
                # category == expected_category and label == item.label
                # The width and height could be off, or we could have edited the file to trigger a change
                width, height = get_dimensions(path)
                edit_item(item_id=item.id, new_height=height, new_width=width)

                return

            # No other branches possible.

        else:
            # File does not have a database entry, create it
            upload_item(path)

    def handle_delete(self, path):
        if os.path.exists(path):
            return

        # Check if item exists and matches its database entry

        item, _ = try_get_item(path)
        if item is not None:
            if not os.path.exists(item.getpath()):
                item.delete()


class MyEventHandler(FileSystemEventHandler):
    def __init__(self, event_processor):
        super(FileSystemEventHandler, self).__init__()
        self.event_processor = event_processor

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return

        paths = []
        if hasattr(event, "src_path"):
            paths.append(event.src_path)

        if hasattr(event, "dest_path"):
            paths.append(event.dest_path)

        for path in paths:
            if not path or "." not in path:
                continue

            # Types are deleted, created, modified
            self.event_processor.add(
                path, "deleted" if event.event_type == "deleted" else "created"
            )


def preprocess_watchdog_listener(directories=None):
    if directories is None:
        directories = [*READER_PATHS, MEDIA_PATH]
    directories = [path for path in directories if path]
    # Add initial changes (unprocessed, media paths)
    for directory in directories:
        read_directory(directory)

    clean_db()


def run_watchdog_listener(directories=None):
    if directories is None:
        directories = [*READER_PATHS, MEDIA_PATH]
    directories = [path for path in directories if path]
    processor = EventProcessor()
    event_handler = MyEventHandler(processor)

    observer = Observer()
    for directory in directories:
        if os.path.exists(directory):
            observer.schedule(event_handler, directory, recursive=True)
    observer.start()

    while True:
        processor.process()
        VideoRemover.process()
        time.sleep(PROCESS_TIME)


def read_directory(directory_path):
    if not os.path.exists(directory_path):
        return

    for root, _, files in os.walk(directory_path):
        root = root.replace("\\", "/")

        # Dropbox edge case handling
        if ".cache" in root:
            continue

        for file in files:
            path = f"{root}/{file}".replace("\\", "/")

            filename = path.split("/")[-1]

            banned_subnames = ("dropbox", ".ini")
            if any(banned_sn in filename for banned_sn in banned_subnames):
                continue

            EventProcessor.handle_check(path, compare_edits=False)
