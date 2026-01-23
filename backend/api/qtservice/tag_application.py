from api.views_extension import (
    get_next_tag_item,
    delete_items,
    edit_item,
    get_tags,
    get_latest_confirmed_item,
    add_tags,
    get_distinct_tags,
    remove_tags,
)
from api.models import Item, FileType, FileState
from api.utils.overrides import PRIORITY_TAG_MAP, PRIORITY_COLORS
from collections import defaultdict, deque
from functools import partial
import sys
import os
import platform

from PySide6 import QtCore, QtGui, QtWidgets
import vlc


VIDEO_CACHE_MS = 200
MAX_PREVIOUS_IDS = 1000

BANNED_TAGS = ("label", "filetype")

CONFIRMED_COLOR = "#00FF00"

COLOR_DATA = [
    ("black", "#000000", -3, 1),
    ("white", "#EEEEEE", -1, 2),
    ("grey", "#808080", -2, 1),
    ("red", "#FF0000", 1, 2),
    ("yellow", "#E1C223", 21, 2),
    ("lightblue", "#ADD8E6", 47, 2),
    ("blue", "#525DBE", 50, 2),
    ("green", "#1CE31C", 31, 2),
    ("orange", "#FF8000", 12, 2),
    ("purple", "#AE35AE", 65, 2),
    ("pink", "#FB8AC8", 9, 3),
    ("brown", "#593915", 17, 3),
    ("navy", "#000080", 53, 3),
    ("cream", "#FFFDD0", 90, 3),
    ("beige", "#F9BF79", 94, 3),
    ("burgundy", "#6E2525", 5, 3),
    ("olive", "#556B2F", 34, 3),
    ("teal", "#008080", 44, 4),
    ("salmon", "#FA8072", 7, 4),
    ("peach", "#FFDAB9", 11, 4),
    ("khaki", "#F0E68C", 26, 4),
    ("tan", "#D2B48C", 93, 4),
]
COLOR_DATA_NAMES = set([i[0] for i in COLOR_DATA])


class VlcVideoWidget(QtWidgets.QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WA_NativeWindow)
        self.setStyleSheet("background-color: black;")
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
        )
        self._instance = vlc.Instance(
            [
                "--no-audio",
                "--no-video-title-show",
                "--avcodec-hw=any",
                f"--file-caching={VIDEO_CACHE_MS}",
                "--quiet",
            ]
        )
        self._player = self._instance.media_player_new()
        self._media = None
        self._is_bound = False
        self._loop = True
        self._event_manager = self._player.event_manager()
        self._event_manager.event_attach(
            vlc.EventType.MediaPlayerEndReached, self._on_end
        )

    def bind_player(self):
        if self._is_bound:
            return
        handle = int(self.winId())
        system = platform.system()
        if system == "Windows":
            self._player.set_hwnd(handle)
        elif system == "Linux":
            self._player.set_xwindow(handle)
        elif system == "Darwin":
            self._player.set_nsobject(handle)
        self._is_bound = True

    def set_media(self, path, loop=True):
        self.bind_player()
        self._loop = loop
        self._media = self._instance.media_new(path)
        if loop:
            self._media.add_option("input-repeat=65535")
        self._player.set_media(self._media)
        self._player.audio_set_mute(True)
        self._player.video_set_scale(0)
        self._player.video_set_aspect_ratio("")

    def play(self):
        if self._media:
            self._player.play()

    def stop(self):
        self._player.stop()

    def _on_end(self, event):
        if self._loop:
            self._player.stop()
            self._player.play()

    def close(self):
        try:
            self.stop()
        finally:
            self._player.release()
            self._instance.release()


class TagApplication(QtWidgets.QMainWindow):
    def __init__(self, tag_random=False):
        super().__init__()
        self.tag_random = tag_random
        self.item_id = None
        self.item = None
        self.media_widget = None
        self.media_label = None
        self.tag_query_width = 0
        self.partials_to_execute = []
        self.previous_ids = deque()
        self.window_closed_manually = False
        self.completed = False
        self.widget_width = 0
        self.widget_height = 0
        self._screen_geometry = None
        self._resize_timer = QtCore.QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(150)
        self._resize_timer.timeout.connect(self._on_resize_timeout)

        self.setWindowTitle("Tag application")
        screen = QtGui.QGuiApplication.primaryScreen()
        if screen:
            self._screen_geometry = screen.availableGeometry()
            width = int(self._screen_geometry.width() * 0.85)
            height = int(self._screen_geometry.height() * 0.85)
            self.resize(width, height)
        else:
            self.resize(1500, 900)

        self._build_ui()
        self._apply_dark_theme()
        self.load_next_item()

    def _build_ui(self):
        root = QtWidgets.QWidget(self)
        self.setCentralWidget(root)

        self.main_layout = QtWidgets.QHBoxLayout(root)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(10)

        # Media panel
        self.media_container = QtWidgets.QFrame()
        self.media_container.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.media_container.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
        )
        self.media_layout = QtWidgets.QVBoxLayout(self.media_container)
        self.media_layout.setContentsMargins(0, 0, 0, 0)
        self.media_layout.setSpacing(6)

        self.media_area = QtWidgets.QStackedWidget()
        self.media_area.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
        )
        self.media_area.setMinimumSize(1, 1)
        self.media_layout.addWidget(self.media_area, 1)

        button_row = QtWidgets.QHBoxLayout()
        self.confirm_button = QtWidgets.QPushButton("Confirm")
        self.delete_button = QtWidgets.QPushButton("Delete")
        button_row.addWidget(self.delete_button)
        button_row.addWidget(self.confirm_button)
        self.media_layout.addLayout(button_row)

        # Tag panel
        self.tag_container = QtWidgets.QFrame()
        self.tag_container.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.tag_container.setSizePolicy(
            QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Expanding
        )
        self.tag_container.setMinimumWidth(300)
        self.tag_layout = QtWidgets.QVBoxLayout(self.tag_container)
        self.tag_layout.setContentsMargins(8, 8, 8, 8)
        self.tag_layout.setSpacing(8)

        # Current tags
        current_label = QtWidgets.QLabel("Current Tags")
        current_label.setStyleSheet("font-weight: bold;")
        self.tag_layout.addWidget(current_label)

        self.tag_scroll = QtWidgets.QScrollArea()
        self.tag_scroll.setWidgetResizable(True)
        self.tag_scroll_contents = QtWidgets.QWidget()
        self.tag_scroll_layout = QtWidgets.QVBoxLayout(self.tag_scroll_contents)
        self.tag_scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.tag_scroll_layout.setSpacing(6)
        self.tag_scroll.setWidget(self.tag_scroll_contents)
        self.tag_layout.addWidget(self.tag_scroll, 2)

        # Suggested tags
        self.suggested_header = QtWidgets.QHBoxLayout()
        suggested_label = QtWidgets.QLabel("Suggested")
        suggested_label.setStyleSheet("font-weight: bold;")
        self.suggested_header.addWidget(suggested_label)
        self.commit_button = QtWidgets.QPushButton("Commit")
        self.clear_button = QtWidgets.QPushButton("Clear")
        self.suggested_header.addStretch(1)
        self.suggested_header.addWidget(self.commit_button)
        self.suggested_header.addWidget(self.clear_button)
        self.tag_layout.addLayout(self.suggested_header)

        self.suggested_scroll = QtWidgets.QScrollArea()
        self.suggested_scroll.setWidgetResizable(True)
        self.suggested_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.suggested_scroll_contents = QtWidgets.QWidget()
        self.suggested_scroll_layout = QtWidgets.QVBoxLayout(
            self.suggested_scroll_contents
        )
        self.suggested_scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.suggested_scroll_layout.setSpacing(6)
        self.suggested_scroll.setWidget(self.suggested_scroll_contents)
        self.tag_layout.addWidget(self.suggested_scroll, 3)

        self.main_layout.addWidget(self.media_container, 1)
        self.main_layout.addWidget(self.tag_container, 1)

        self.confirm_button.clicked.connect(self.confirm)
        self.delete_button.clicked.connect(self.delete)
        self.commit_button.clicked.connect(self.commit_and_reload)
        self.clear_button.clicked.connect(self.clear_commit_and_reload)

        self.shortcut_confirm = QtGui.QShortcut(QtGui.QKeySequence("Return"), self)
        self.shortcut_confirm.activated.connect(self.confirm)
        self.shortcut_delete = QtGui.QShortcut(QtGui.QKeySequence("Delete"), self)
        self.shortcut_delete.activated.connect(self.delete)
        self.shortcut_revoke = QtGui.QShortcut(QtGui.QKeySequence("-"), self)
        self.shortcut_revoke.activated.connect(self.revoke_last)

    def _apply_dark_theme(self):
        self.setStyleSheet(
            """
            QMainWindow { background-color: #1C1D21; color: #E6E6E6; }
            QWidget { background-color: #1C1D21; color: #E6E6E6; }
            QLineEdit {
                background-color: #24262B;
                border: 1px solid #3A3D44;
                padding: 4px;
                color: #E6E6E6;
            }
            QPushButton {
                background-color: #2B2E35;
                border: 1px solid #3A3D44;
                padding: 4px 8px;
            }
            QPushButton:disabled {
                background-color: #2B2E35;
                color: #6E7179;
            }
            QScrollArea { border: 1px solid #2C2E34; }
            QScrollBar:vertical { background: #1C1D21; width: 12px; margin: 2px; }
            QScrollBar::handle:vertical { background: #3A3D44; min-height: 20px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            """
        )

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
            else:
                child_layout = item.layout()
                if child_layout:
                    self._clear_layout(child_layout)

    def clear_media_area(self):
        for i in reversed(range(self.media_area.count())):
            widget = self.media_area.widget(i)
            self.media_area.removeWidget(widget)
            widget.deleteLater()

        if self.media_widget:
            self.media_widget.close()
            self.media_widget = None

        self.media_label = None

    def _close_media_player(self):
        if self.media_widget:
            self.media_widget.close()
            self.media_widget = None

    def load_next_item(self):
        self.item_id = get_next_tag_item(self.tag_random)
        if self.item_id is None:
            self.completed = True
            self.close()
            return

        self.item = Item.objects.filter(id=self.item_id).get()
        self.setWindowTitle(f"Tag application - Item {self.item_id}")

        self.load_media()
        self.load_tags()

    def _estimate_widget_size(self):
        if not self.item:
            return
        window_height = max(self.height(), 1)
        window_margins = self.main_layout.contentsMargins()
        window_padding = window_margins.top() + window_margins.bottom()
        media_margins = self.media_layout.contentsMargins()
        media_padding = media_margins.top() + media_margins.bottom()
        media_padding += max(self.media_layout.spacing(), 0)
        button_hint = self.confirm_button.sizeHint().height()
        max_height = max(
            window_height - (window_padding + media_padding + button_hint), 200
        )

        new_width = int(round(self.item.width * max_height / self.item.height))
        new_height = max_height
        self.widget_width = new_width
        self.widget_height = new_height
        self.media_container.setMinimumWidth(new_width)
        if hasattr(self, "main_layout"):
            total_width = max(self.width(), 1)
            image_stretch = max(1, int(self.widget_width))
            tag_stretch = max(1, int(max(total_width - self.widget_width, 1)))
            self.main_layout.setStretch(0, image_stretch)
            self.main_layout.setStretch(1, tag_stretch)

    def load_media(self):
        self.clear_media_area()
        self._estimate_widget_size()

        if self.item.filetype == int(FileType.Image):
            self.media_label = QtWidgets.QLabel(alignment=QtCore.Qt.AlignCenter)
            self.media_label.setStyleSheet("background-color: #1C1D21;")
            self.media_label.setSizePolicy(
                QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Ignored
            )
            self.media_label.setMinimumSize(1, 1)
            self.media_label.mousePressEvent = lambda event: self.open_item()
            self.media_area.addWidget(self.media_label)
            self.media_area.setCurrentWidget(self.media_label)
            QtCore.QTimer.singleShot(0, self._refresh_media_scale)
        elif self.item.filetype == int(FileType.Video):
            self.media_widget = VlcVideoWidget()
            self.media_area.addWidget(self.media_widget)
            self.media_area.setCurrentWidget(self.media_widget)
            self.media_widget.mousePressEvent = lambda event: self.open_item()
            self.media_widget.set_media(self.item.getpath(), loop=True)
            self.media_widget.play()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._estimate_widget_size()
        self._refresh_media_scale()
        if self.item:
            self._resize_timer.start()

    def _on_resize_timeout(self):
        if self.item:
            self.load_tags(commit=False)

    def load_tags(self, commit=True):
        if commit:
            self.commit()
        self._clear_layout(self.tag_scroll_layout)
        self._clear_layout(self.suggested_scroll_layout)

        tags = get_tags(self.item_id)

        tag_name_value_pairs = []
        tag_names_set = set()

        for tag_name, tag_values in tags.items():
            for value in tag_values:
                if tag_name in BANNED_TAGS:
                    continue
                tag_name_value_pairs.append((tag_name, value))
                tag_names_set.add(tag_name)

        tag_name_value_pairs.sort(key=lambda x: x[0])

        for banned_tag in reversed(BANNED_TAGS):
            banned_value = tags.get(banned_tag, [""])[0]
            tag_name_value_pairs.insert(0, (banned_tag, banned_value))

        tag_name_value_pairs.append(("", ""))

        for tag_name, tag_value in tag_name_value_pairs:
            row = QtWidgets.QWidget()
            row_layout = QtWidgets.QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(3)

            name_entry = QtWidgets.QLineEdit()
            name_entry.setText(tag_name)
            value_entry = QtWidgets.QLineEdit()
            value_entry.setText(tag_value)
            row_height = max(name_entry.sizeHint().height(), 28)
            name_entry.setFixedHeight(row_height)
            value_entry.setFixedHeight(row_height)

            row_layout.addWidget(name_entry, 1)
            row_layout.addWidget(value_entry, 1)

            if tag_name in BANNED_TAGS:
                submit_button = QtWidgets.QPushButton("+")
                submit_button.setEnabled(False)
                remove_button = QtWidgets.QPushButton("x")
                remove_button.setEnabled(False)
                if tag_name == "label":
                    submit_button.setEnabled(True)
                    submit_button.clicked.connect(
                        partial(self.new_label, value_entry=value_entry)
                    )
            else:
                submit_button = QtWidgets.QPushButton("+")
                submit_button.clicked.connect(
                    partial(
                        self.update_tags,
                        name_entry=name_entry,
                        value_entry=value_entry,
                        old_name=tag_name,
                        old_value=tag_value,
                        reset_tags=True,
                    )
                )
                remove_button = QtWidgets.QPushButton("x")
                remove_button.clicked.connect(
                    partial(
                        self.update_tags,
                        name_entry=EmptyEntry(),
                        value_entry=EmptyEntry(),
                        old_name=tag_name,
                        old_value=tag_value,
                        reset_tags=True,
                    )
                )
            for button in (submit_button, remove_button):
                button.setFixedHeight(row_height)
                row_layout.addWidget(button, 0)

            self.tag_scroll_layout.addWidget(row)

        self.tag_scroll_layout.addStretch(1)

        self._load_suggested_tags(tags, tag_names_set, tag_name_value_pairs)

    def _load_suggested_tags(self, tags, tag_names_set, tag_name_value_pairs):
        provided_query_width = self.tag_query_width

        query_size = 105
        tag_label_width = 160
        small_colour_width = 20

        if provided_query_width == 0:
            initial_tag_setup_width = 400
            space = max(self.width() - self.media_container.width(), 0)
            if space < initial_tag_setup_width:
                provided_query_width = 2
            else:
                provided_query_width = (space - tag_label_width) // query_size
                provided_query_width = max(2, provided_query_width)

        colour_space = query_size * provided_query_width + tag_label_width

        if small_colour_width * len(COLOR_DATA) <= colour_space - tag_label_width:
            provided_colour_size = 1
            while (small_colour_width + 6 * (provided_colour_size - 1)) * len(
                COLOR_DATA
            ) <= colour_space - tag_label_width:
                provided_colour_size += 1
            provided_colour_size -= 1

            expected_width = small_colour_width + 6 * (provided_colour_size - 1)
            provided_colour_width = (colour_space - tag_label_width) // (expected_width)
            can_fit_all_colours = True
        else:
            provided_colour_size = 1
            provided_colour_width = (
                colour_space - tag_label_width - query_size
            ) // small_colour_width
            can_fit_all_colours = False

        provided_query_width = int(provided_query_width)
        provided_colour_width = int(provided_colour_width)

        tags_to_display = defaultdict(dict)

        label_values = tags.get("label", [])
        latest_label_ids = None
        if label_values:
            latest_label_ids = get_latest_confirmed_item(label=label_values[0])

        if latest_label_ids is not None:
            for latest_label_id in latest_label_ids:
                suggested_tags_d = get_tags(latest_label_id)
                for tag_name, tag_values in suggested_tags_d.items():
                    if tag_name in BANNED_TAGS or (
                        tag_name in tag_names_set and tag_name != "labelplus"
                    ):
                        continue
                    for value in tag_values:
                        if (tag_name, value) in tag_name_value_pairs:
                            continue

                        if tag_name not in tags_to_display:
                            tags_to_display[tag_name] = {
                                "values": [value],
                                "priority": PRIORITY_TAG_MAP.get(tag_name, 1),
                            }

                        elif (
                            len(tags_to_display[tag_name]["values"])
                            < provided_query_width
                            and value not in tags_to_display[tag_name]["values"]
                        ):
                            tags_to_display[tag_name]["values"].append(value)

        latest_distinct = get_distinct_tags()
        for tag_name, value in latest_distinct:
            if tag_name in BANNED_TAGS or (
                tag_name in tag_names_set and tag_name != "labelplus"
            ):
                continue
            if (tag_name, value) in tag_name_value_pairs:
                continue

            if tag_name not in tags_to_display:
                tags_to_display[tag_name] = {
                    "values": [value],
                    "priority": PRIORITY_TAG_MAP.get(tag_name, 0),
                }

            elif (
                len(tags_to_display[tag_name]["values"]) < provided_query_width
                and value not in tags_to_display[tag_name]["values"]
            ):
                tags_to_display[tag_name]["values"].append(value)

        tag_items = [
            (name, tag["values"], tag["priority"])
            for name, tag in tags_to_display.items()
        ]
        tag_items.sort(key=lambda x: x[0])
        tag_items.sort(key=lambda x: x[2])

        tag_items.append(("", [], 0))

        colours = [i for i in COLOR_DATA]
        colours.sort(key=lambda x: x[3])
        colours.sort(key=lambda x: x[2])
        font_metrics = QtGui.QFontMetrics(self.font())
        max_name_width = 0
        for tag_name, _, _ in tag_items:
            max_name_width = max(
                max_name_width, font_metrics.horizontalAdvance(tag_name)
            )
        max_name_width = max(40, max_name_width + 16)
        max_colour_buttons = None
        if self.suggested_scroll.viewport():
            viewport_width = max(self.suggested_scroll.viewport().width(), 1)
            label_width = int(tag_label_width)
            min_button_width = 8
            available = max(viewport_width - label_width, min_button_width)
            max_colour_buttons = max(1, available // min_button_width)

        def _is_colour_value(value):
            return value in COLOR_DATA_NAMES or value in ("any", "none")

        for i, tag_entry in enumerate(tag_items):
            tag_name, tag_values, priority = tag_entry

            row = QtWidgets.QWidget()
            row_layout = QtWidgets.QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(3)

            tag_entry_name = QtWidgets.QLineEdit()
            tag_entry_name.setText(tag_name)
            tag_entry_name.setFixedWidth(max_name_width)
            row_height = max(tag_entry_name.sizeHint().height(), 28)
            tag_entry_name.setFixedHeight(row_height)
            if priority != 0:
                priority_fg, priority_bg = PRIORITY_COLORS[priority]
                tag_entry_name.setStyleSheet(
                    f"color: {priority_fg}; background-color: {priority_bg};"
                )

            row_layout.addWidget(tag_entry_name, 0, QtCore.Qt.AlignLeft)

            if tag_values and all(_is_colour_value(v) for v in tag_values):
                row_layout.setSpacing(0)
                row_layout.setAlignment(QtCore.Qt.AlignLeft)
                row_colours = list(colours)
                if not can_fit_all_colours:
                    partial_cmd = partial(
                        self.update_tags,
                        name_entry=tag_entry_name,
                        value_entry=StaticEntry(""),
                        old_name="",
                        old_value="",
                        reset_tags=False,
                    )

                    tag_entry_submit = QtWidgets.QPushButton("Add")
                    tag_entry_submit.setFixedWidth(36)
                    tag_entry_submit.setFixedHeight(row_height)
                    tag_entry_submit.clicked.connect(
                        partial(self.add_partial, partial_cmd, tag_entry_submit)
                    )

                    row_layout.addWidget(tag_entry_submit, 0)

                    row_colours.sort(key=lambda x: x[3])
                    row_colours = row_colours[:provided_colour_width]
                    row_colours.sort(key=lambda x: x[2])

                if max_colour_buttons is not None and max_colour_buttons < len(
                    row_colours
                ):
                    row_colours = row_colours[:max_colour_buttons]

                for idx, color_data in enumerate(row_colours):
                    tag_value = color_data[0]
                    tag_color = color_data[1]

                    partial_cmd = partial(
                        self.update_tags,
                        name_entry=tag_entry_name,
                        value_entry=StaticEntry(tag_value),
                        old_name="",
                        old_value="",
                        reset_tags=False,
                    )

                    tag_entry_submit = QtWidgets.QPushButton("")
                    tag_entry_submit.setFixedHeight(row_height)
                    tag_entry_submit.setMinimumWidth(8)
                    tag_entry_submit.setSizePolicy(
                        QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
                    )
                    tag_entry_submit.clicked.connect(
                        partial(self.add_partial, partial_cmd, tag_entry_submit)
                    )
                    tag_entry_submit.setToolTip(tag_value)

                    tag_entry_submit.setStyleSheet(
                        f"background-color: {tag_color}; padding: 0px;"
                    )

                    row_layout.addWidget(tag_entry_submit, 1)

            else:
                for j in range(provided_query_width):
                    if j >= len(tag_values):
                        tag_value = ""
                    else:
                        tag_value = tag_values[j]

                    tag_entry_value = QtWidgets.QLineEdit()
                    tag_entry_value.setText(tag_value)
                    tag_entry_value.setFixedHeight(row_height)
                    partial_cmd = partial(
                        self.update_tags,
                        name_entry=tag_entry_name,
                        value_entry=tag_entry_value,
                        old_name="",
                        old_value="",
                        reset_tags=False,
                    )

                    tag_entry_submit = QtWidgets.QPushButton("")
                    tag_entry_submit.setFixedWidth(14)
                    tag_entry_submit.setFixedHeight(row_height)
                    tag_entry_submit.setStyleSheet("padding: 0px;")
                    tag_entry_submit.clicked.connect(
                        partial(self.add_partial, partial_cmd, tag_entry_submit)
                    )

                    row_layout.addWidget(tag_entry_value, 1)
                    row_layout.addWidget(tag_entry_submit, 0)

            self.suggested_scroll_layout.addWidget(row)

        self.suggested_scroll_layout.addStretch(1)

    def _entry_text(self, entry):
        if hasattr(entry, "text"):
            return entry.text()
        return entry.get()

    def _refresh_media_scale(self):
        if not (self.media_label and self.item):
            return
        if self.item.filetype != int(FileType.Image):
            return
        pixmap = QtGui.QPixmap(self.item.getpath())
        if pixmap.isNull():
            return
        target_size = self.media_area.size()
        if target_size.width() <= 1 or target_size.height() <= 1:
            return
        self.media_label.setPixmap(
            pixmap.scaled(
                target_size,
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation,
            )
        )

    def update_tags(
        self, name_entry, value_entry, old_name, old_value, reset_tags=True, event=None
    ):
        new_name = self._entry_text(name_entry).strip().lower()
        new_value = self._entry_text(value_entry).strip().lower()

        if old_name == new_name and old_value == new_value:
            return

        if old_name != "" and old_value != "":
            remove_tags({self.item_id: {old_name: [old_value]}})

        if new_name != "" and new_value != "":
            add_tags({self.item_id: {new_name: [new_value]}})

            for t in ("top", "bottom"):
                if new_name in (f"{t}color", f"{t}type") and new_value in (
                    "any",
                    "none",
                ):
                    add_tags(
                        {
                            self.item_id: {
                                f"{t}color": [new_value],
                                f"{t}type": [new_value],
                            }
                        }
                    )

        if reset_tags:
            self.load_tags()

    def new_label(self, value_entry, event=None):
        new_value = value_entry.text().strip().lower()
        if new_value == "":
            return

        if self.item and self.item.filetype == int(FileType.Video):
            self._close_media_player()
        self.commit()
        edit_item(self.item_id, new_label=new_value, new_state=int(FileState.NeedsTags))
        self.load_next_item()

    def commit(self):
        for p in self.partials_to_execute:
            p()
        self.partials_to_execute = []

    def commit_and_reload(self):
        self.commit()
        self.load_tags(commit=False)

    def clear_commit_and_reload(self):
        self.partials_to_execute = []
        self.load_tags(commit=False)

    def clear_commit_and_next(self):
        self.partials_to_execute = []
        self.load_next_item()

    def add_partial(self, partial_fn, button, event=None):
        self.partials_to_execute.append(partial_fn)
        button.setStyleSheet(
            f"color: {CONFIRMED_COLOR}; background-color: {CONFIRMED_COLOR}; "
            "border: 3px solid #B23A3A;"
        )
        button.setEnabled(False)

    def revoke_last(self):
        if not self.previous_ids:
            return
        last_id = self.previous_ids.pop()
        edit_item(last_id, new_state=int(FileState.NeedsTags))
        self.clear_commit_and_next()

    def confirm(self):
        self.commit()
        edit_item(item_id=self.item_id, new_state=int(FileState.Complete))
        if self.item_id is not None:
            self.previous_ids.append(self.item_id)
            while len(self.previous_ids) > MAX_PREVIOUS_IDS:
                self.previous_ids.popleft()
        self.load_next_item()

    def delete(self):
        delete_items(item_ids=(self.item_id,))
        self.clear_commit_and_next()

    def open_item(self):
        os.startfile(self.item.getpath())

    def closeEvent(self, event):
        if self.media_widget:
            self.media_widget.close()
        if not self.completed:
            self.window_closed_manually = True
        super().closeEvent(event)


class EmptyEntry:
    def get(self):
        return ""


class StaticEntry:
    def __init__(self, value):
        self._value = value

    def get(self):
        return self._value


def start_tag_application(tag_random=False):
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)
    window = TagApplication(tag_random=tag_random)
    window.showMaximized()
    window.raise_()
    window.activateWindow()
    app.exec()
    return not window.window_closed_manually, window.completed


if __name__ == "__main__":
    start_tag_application()
