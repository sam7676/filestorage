from api.views_extension import (
    TagConditions,
    get_thumbnail,
    get_items_and_paths_from_tags,
    get_tag,
    get_tags,
    TAG_STYLE_OPTIONS,
    delete_items,
    edit_item,
)
from api.models import Item, FileType, FileState
from collections import defaultdict
from functools import partial
import random
import sys
import os
from PIL import ImageQt
from PySide6 import QtCore, QtGui, QtWidgets
import vlc
from api.utils.overrides import get_view_default_tags


SORT_METRIC_OPTIONS = ("alphabetical", "random")
VIDEOS_CURRENTLY_PLAYED = 2


class VlcVideoWidget(QtWidgets.QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WA_NativeWindow)
        self.setStyleSheet("background-color: #1C1D21;")
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
        )
        self._instance = vlc.Instance(
            [
                "--no-audio",
                "--no-video-title-show",
                "--avcodec-hw=any",
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
        system = QtCore.QSysInfo.productType()
        if system == "windows":
            self._player.set_hwnd(handle)
        elif system == "osx":
            self._player.set_nsobject(handle)
        else:
            self._player.set_xwindow(handle)
        self._is_bound = True

    def set_media(self, path, loop=True):
        self.bind_player()
        self._media = self._instance.media_new(path)
        self._loop = loop
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


class ViewApplication(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.window_closed_manually = False
        self.completed = False

        self.items_per_bin = 0
        self.items_per_window = 2
        self.page_increment_rate = 1
        self.max_bin_videos = 1
        self.videos_currently_played = VIDEOS_CURRENTLY_PLAYED

        self.item_ids = []
        self.id_data = {}
        self.bins = defaultdict(list)
        self.bin_group_metric = "label"
        self.sort_metric_option = "alphabetical"
        self.orderby_metric = "random"
        self.orderby_usenull = True
        self.modify_mode = False
        self.thumbnail_mode = False

        self.chosen_tags = get_view_default_tags()
        self.current_page = 0
        self.max_page = 0
        self.page_data = []
        self.sorted_bin_metrics = []

        self.setWindowTitle("View")
        screen = QtGui.QGuiApplication.primaryScreen()
        if screen:
            geometry = screen.availableGeometry()
            width = int(geometry.width() * 0.9)
            height = int(geometry.height() * 0.9)
            self.resize(width, height)
        else:
            self.resize(1500, 900)

        self.tag_panel_width = 380
        self._update_page_dimensions()

        self._build_ui()
        self._apply_dark_theme()
        self.get_ids_and_build_bins()
        self.load_items()
        self.load_chosen_tags()

    def _build_ui(self):
        root = QtWidgets.QWidget(self)
        self.setCentralWidget(root)

        layout = QtWidgets.QHBoxLayout(root)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        self.item_panel = QtWidgets.QWidget()
        self.item_layout = QtWidgets.QVBoxLayout(self.item_panel)
        self.item_layout.setContentsMargins(0, 0, 0, 0)
        self.item_layout.setSpacing(0)

        self.items_scroll = QtWidgets.QScrollArea()
        self.items_scroll.setWidgetResizable(True)
        self.items_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.items_scroll_contents = QtWidgets.QWidget()
        self.items_scroll_layout = QtWidgets.QVBoxLayout(self.items_scroll_contents)
        self.items_scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.items_scroll_layout.setSpacing(0)
        self.items_scroll.setWidget(self.items_scroll_contents)

        self.item_layout.addWidget(self.items_scroll, 1)
        self._build_page_controls()
        self.item_layout.addWidget(self.page_container, 0)

        self.tag_panel = QtWidgets.QWidget()
        self.tag_layout = QtWidgets.QVBoxLayout(self.tag_panel)
        self.tag_layout.setContentsMargins(0, 0, 0, 0)
        self.tag_layout.setSpacing(6)
        self.tag_panel.setFixedWidth(self.tag_panel_width)

        self.tag_scroll = QtWidgets.QScrollArea()
        self.tag_scroll.setWidgetResizable(True)
        self.tag_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.tag_scroll_contents = QtWidgets.QWidget()
        self.tag_scroll_layout = QtWidgets.QVBoxLayout(self.tag_scroll_contents)
        self.tag_scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.tag_scroll_layout.setSpacing(6)
        self.tag_scroll.setWidget(self.tag_scroll_contents)

        self.tag_layout.addWidget(self.tag_scroll, 1)

        layout.addWidget(self.item_panel, 5)
        layout.addWidget(self.tag_panel, 1)

        QtGui.QShortcut(QtGui.QKeySequence("PgUp"), self, activated=self.decrement_page)
        QtGui.QShortcut(
            QtGui.QKeySequence("PgDown"), self, activated=self.increment_page
        )
        QtGui.QShortcut(QtGui.QKeySequence("Up"), self, activated=self.decrement_page)
        QtGui.QShortcut(QtGui.QKeySequence("Down"), self, activated=self.increment_page)
        QtGui.QShortcut(QtGui.QKeySequence("Left"), self, activated=self.decrement_page)
        QtGui.QShortcut(
            QtGui.QKeySequence("Right"), self, activated=self.increment_page
        )

        QtGui.QShortcut(
            QtGui.QKeySequence("Shift+Up"), self, activated=self.decrement_page_person
        )
        QtGui.QShortcut(
            QtGui.QKeySequence("Shift+Down"), self, activated=self.increment_page_person
        )
        QtGui.QShortcut(
            QtGui.QKeySequence("Shift+Left"), self, activated=self.decrement_page_person
        )
        QtGui.QShortcut(
            QtGui.QKeySequence("Shift+Right"),
            self,
            activated=self.increment_page_person,
        )

        QtGui.QShortcut(QtGui.QKeySequence("F5"), self, activated=self.random_page)
        QtGui.QShortcut(QtGui.QKeySequence("Return"), self, activated=self.random_page)

    def _build_page_controls(self):
        page_row = QtWidgets.QHBoxLayout()
        self.page_super_prev = QtWidgets.QPushButton("<<")
        self.page_prev = QtWidgets.QPushButton("<")
        self.page_current = QtWidgets.QLabel("0 / 0")
        self.page_next = QtWidgets.QPushButton(">")
        self.page_super_next = QtWidgets.QPushButton(">>")

        self.page_super_prev.clicked.connect(self.decrement_page_person)
        self.page_prev.clicked.connect(self.decrement_page)
        self.page_next.clicked.connect(self.increment_page)
        self.page_super_next.clicked.connect(self.increment_page_person)

        page_row.addWidget(self.page_super_prev)
        page_row.addWidget(self.page_prev)
        page_row.addStretch(1)
        page_row.addWidget(self.page_current)
        page_row.addStretch(1)
        page_row.addWidget(self.page_next)
        page_row.addWidget(self.page_super_next)

        self.page_container = QtWidgets.QWidget()
        self.page_container.setLayout(page_row)

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
                padding: 2px 6px;
            }
            """
        )

    def _update_page_dimensions(self):
        available_width = max(1, self.width() - self.tag_panel_width - 40)
        available_height = max(1, self.height() - 140)
        self.page_width = available_width
        self.page_height = available_height

    def get_new_size(self, width, height):
        new_item_height = self.page_height // self.items_per_window
        new_width = int(round(width * new_item_height / height))
        new_height = new_item_height
        if new_width > self.page_width:
            new_width = self.page_width
            new_height = int(round(self.page_width / new_width * new_item_height))
        return new_width, new_height

    def clear_video_players(self):
        for item_id, data in list(self.id_data.items()):
            player = data.get("video_widget")
            if player:
                player.close()
                self.id_data[item_id].pop("video_widget", None)

    def get_widget(self, item_id, force_thumbnail=False):
        item = Item.objects.filter(id=item_id).get()
        new_width, new_height = self.get_new_size(item.width, item.height)

        if (
            item.filetype == int(FileType.Video)
            and not self.thumbnail_mode
            and not force_thumbnail
        ):
            widget = VlcVideoWidget()
            widget.setFixedSize(new_width, new_height)
            widget.set_media(item.getpath())
            widget.play()
            self.id_data[item_id]["video_widget"] = widget
            return widget

        resized_image = get_thumbnail(item.id, new_width, new_height)
        qimage = ImageQt.ImageQt(resized_image)
        pixmap = QtGui.QPixmap.fromImage(qimage)
        label = QtWidgets.QLabel()
        label.setPixmap(pixmap)
        label.setFixedSize(new_width, new_height)
        label.setStyleSheet("background-color: #1C1D21;")
        return label

    def get_ids_and_build_bins(self):
        tags = defaultdict(list)
        for z, condition in self.chosen_tags.items():
            name, value = z
            tags[(name, condition)].append(value)

        if not self.orderby_usenull:
            tags[(self.orderby_metric, TagConditions.IsNotNull.value)].append("")

        data = get_items_and_paths_from_tags(tags)
        self.item_ids = list(data.keys())
        self.bins = defaultdict(list)
        ids = [item_id for item_id in self.item_ids]

        if self.orderby_metric != "id":
            if self.orderby_metric == "random":
                random.shuffle(ids)
            else:
                ids.sort(key=lambda x: get_tag(x, self.orderby_metric), reverse=True)

        for item_id in ids:
            item = Item.objects.filter(id=item_id).get()
            item_type = int(item.filetype)
            new_width, new_height = self.get_new_size(item.width, item.height)
            new_width = max(new_width, 108)

            if self.bin_group_metric != "":
                tag_data = get_tags(item_id)
                if self.bin_group_metric not in tag_data:
                    continue
                metric = tag_data[self.bin_group_metric][0]
            else:
                metric = ""

            bin_placed = False
            for bin_obj in self.bins[metric]:
                if bin_obj["width"] + new_width <= self.page_width:
                    if (
                        self.items_per_bin > 0
                        and len(bin_obj["ids"]) + 1 > self.items_per_bin
                    ):
                        continue
                    if self.max_bin_videos > 0 and not self.thumbnail_mode:
                        if (
                            item_type == int(FileType.Video)
                            and bin_obj["video_count"] + 1 > self.max_bin_videos
                        ):
                            continue
                    bin_obj["width"] += new_width
                    bin_obj["ids"].append(item_id)
                    bin_obj["video_count"] += item_type
                    bin_placed = True
                    break

            if not bin_placed:
                bin_obj = {
                    "width": new_width,
                    "ids": [item_id],
                    "metric": metric,
                    "video_count": item_type,
                }
                self.bins[metric].append(bin_obj)

            self.id_data[item_id] = {
                "width": new_width,
                "height": new_height,
                "metric": metric,
                "bin": bin_obj,
            }

        if self.sort_metric_option == "alphabetical":
            self.sorted_bin_metrics = list(sorted(self.bins.keys()))
        else:
            self.sorted_bin_metrics = list(self.bins.keys())
            random.shuffle(self.sorted_bin_metrics)

        self.page_data = []
        for metric in self.sorted_bin_metrics:
            for i, b in enumerate(self.bins[metric]):
                if self.orderby_metric == "random":
                    random.shuffle(b["ids"])
                self.page_data.append((metric, i, b))

        self.max_page = len(self.page_data)
        self.current_page = min(
            self.current_page, max(self.max_page - self.items_per_window, 0)
        )
        self.current_page = max(0, self.current_page)

    def load_items(self):
        self.clear_video_players()
        while self.items_scroll_layout.count():
            item = self.items_scroll_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        self.max_page = len(self.page_data)
        self.current_page = min(
            self.current_page, max(self.max_page - self.items_per_window, 0)
        )
        self.current_page = max(0, self.current_page)

        videos_started = 0
        for r in range(self.items_per_window):
            if r >= len(self.page_data):
                break

            metric, pos_in_metric, bin_obj = self.page_data[self.current_page + r]
            row_frame = QtWidgets.QFrame()
            row_layout = QtWidgets.QHBoxLayout(row_frame)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(0)
            row_layout.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)

            media_container = QtWidgets.QWidget()
            media_layout = QtWidgets.QHBoxLayout(media_container)
            media_layout.setContentsMargins(0, 0, 0, 0)
            media_layout.setSpacing(0)
            media_layout.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)

            for item_id in bin_obj["ids"]:
                item_frame = QtWidgets.QFrame()
                item_frame.setSizePolicy(
                    QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Fixed
                )
                item_layout = QtWidgets.QVBoxLayout(item_frame)
                item_layout.setContentsMargins(0, 0, 0, 0)
                item_layout.setSpacing(0)
                item_layout.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)

                button_container = QtWidgets.QWidget()
                button_row = QtWidgets.QHBoxLayout(button_container)
                button_row.setContentsMargins(0, 0, 0, 0)
                button_row.setSpacing(0)
                button_row.setAlignment(QtCore.Qt.AlignHCenter | QtCore.Qt.AlignVCenter)
                delete_button = QtWidgets.QPushButton("X")
                modify_button = QtWidgets.QPushButton("M")
                label_button = QtWidgets.QPushButton("L")
                tag_button = QtWidgets.QPushButton("T")
                print_button = QtWidgets.QPushButton("P")

                delete_button.clicked.connect(partial(self.delete_id, item_id))
                modify_button.clicked.connect(partial(self.modify_id, item_id))
                label_button.clicked.connect(partial(self.label_id, item_id))
                tag_button.clicked.connect(partial(self.tag_id, item_id))
                print_button.clicked.connect(
                    partial(
                        print,
                        f"{item_id} {Item.objects.filter(id=item_id).get().label}",
                    )
                )

                small_size = QtCore.QSize(16, 16)
                for btn in (
                    delete_button,
                    modify_button,
                    label_button,
                    tag_button,
                    print_button,
                ):
                    btn.setEnabled(self.modify_mode)
                    btn.setFixedSize(small_size)
                    btn.setStyleSheet("padding: 0; margin: 0;")
                    button_row.addWidget(btn)

                item_type = Item.objects.filter(id=item_id).get().filetype
                force_thumbnail = False
                if (
                    item_type == int(FileType.Video)
                    and self.videos_currently_played > 0
                    and videos_started >= self.videos_currently_played
                ):
                    force_thumbnail = True
                media = self.get_widget(item_id, force_thumbnail=force_thumbnail)
                if item_type == int(FileType.Video) and not force_thumbnail:
                    videos_started += 1
                if isinstance(media, QtWidgets.QLabel):
                    media.mousePressEvent = lambda event, item_id=item_id: self.open_id(
                        item_id
                    )
                item_layout.addWidget(media)
                item_layout.addWidget(
                    button_container, 0, QtCore.Qt.AlignHCenter | QtCore.Qt.AlignVCenter
                )
                media_layout.addWidget(item_frame, 0, QtCore.Qt.AlignLeft)

            metric_label = QtWidgets.QLabel(
                f"{metric} [{pos_in_metric + 1}/{len(self.bins[metric])}]"
            )
            metric_label.setStyleSheet("padding: 0; margin: 0;")
            metric_label.setSizePolicy(
                QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Fixed
            )
            label_container = QtWidgets.QWidget()
            label_layout = QtWidgets.QVBoxLayout(label_container)
            label_layout.setContentsMargins(0, 0, 0, 0)
            label_layout.setSpacing(0)
            label_layout.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            label_layout.addWidget(metric_label, 0, QtCore.Qt.AlignRight)
            label_container.setFixedWidth(220)

            row_layout.addWidget(media_container, 1)
            row_layout.addStretch(1)
            row_layout.addWidget(label_container, 0, QtCore.Qt.AlignRight)

            self.items_scroll_layout.addWidget(row_frame)

        self.page_current.setText(
            f"{self.current_page + 1 if self.max_page > 0 else 0} / "
            f"{self.max_page - self.items_per_window + 1 if self.max_page > 0 else 0}"
        )

    def load_chosen_tags(self):
        while self.tag_scroll_layout.count():
            item = self.tag_scroll_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        option_frame = QtWidgets.QWidget()
        option_layout = QtWidgets.QVBoxLayout(option_frame)
        option_layout.setContentsMargins(0, 0, 0, 0)
        option_layout.setSpacing(4)

        def _option_row(name, modify_fn, clear_value, update_fn, insert_txt):
            row = QtWidgets.QHBoxLayout()
            label = QtWidgets.QLabel(name)
            clear_btn = QtWidgets.QPushButton("x")
            dec_btn = QtWidgets.QPushButton("-")
            entry = QtWidgets.QLineEdit()
            entry.setFixedWidth(50)
            entry.setText(str(insert_txt))
            inc_btn = QtWidgets.QPushButton("+")
            upd_btn = QtWidgets.QPushButton("=")

            clear_btn.clicked.connect(partial(modify_fn, -clear_value))
            dec_btn.clicked.connect(partial(modify_fn, -1))
            inc_btn.clicked.connect(partial(modify_fn, 1))
            upd_btn.clicked.connect(partial(update_fn, entry))

            row.addWidget(label)
            row.addWidget(clear_btn)
            row.addWidget(dec_btn)
            row.addWidget(entry)
            row.addWidget(inc_btn)
            row.addWidget(upd_btn)
            container = QtWidgets.QWidget()
            container.setLayout(row)
            option_layout.addWidget(container)

        _option_row(
            "Bin size",
            self.modify_items_per_bin,
            self.items_per_bin,
            self.update_items_per_bin,
            self.items_per_bin if self.items_per_bin > 0 else "",
        )
        _option_row(
            "Window size",
            self.modify_items_per_window,
            self.items_per_window,
            self.update_items_per_window,
            self.items_per_window,
        )
        _option_row(
            "Page increment",
            self.modify_page_increment,
            self.page_increment_rate,
            self.update_page_increment,
            self.page_increment_rate,
        )
        _option_row(
            "Video bin count",
            self.modify_video_bin_count,
            self.max_bin_videos,
            self.update_video_bin_count,
            self.max_bin_videos if self.max_bin_videos > 0 else "",
        )
        _option_row(
            "Videos at once",
            self.modify_videos_currently_played,
            self.videos_currently_played,
            self.update_videos_currently_played,
            self.videos_currently_played if self.videos_currently_played > 0 else "",
        )

        metric_row = QtWidgets.QHBoxLayout()
        metric_label = QtWidgets.QLabel("Metric")
        metric_clear = QtWidgets.QPushButton("x")
        metric_entry = QtWidgets.QLineEdit()
        metric_entry.setText(self.bin_group_metric)
        metric_btn = QtWidgets.QPushButton("+")
        metric_clear.clicked.connect(self.remove_bin_group_metric)
        metric_btn.clicked.connect(partial(self.update_bin_group_metric, metric_entry))
        metric_row.addWidget(metric_label)
        metric_row.addWidget(metric_clear)
        metric_row.addWidget(metric_entry)
        metric_row.addWidget(metric_btn)
        metric_container = QtWidgets.QWidget()
        metric_container.setLayout(metric_row)
        option_layout.addWidget(metric_container)

        order_row = QtWidgets.QHBoxLayout()
        order_label = QtWidgets.QLabel("Order by")
        order_clear = QtWidgets.QPushButton("x")
        order_entry = QtWidgets.QLineEdit()
        order_entry.setText(self.orderby_metric)
        order_btn = QtWidgets.QPushButton("~")
        order_null = QtWidgets.QPushButton("Use null")
        order_null.setStyleSheet(
            "color: #6dd36d;" if self.orderby_usenull else "color: #ff6666;"
        )
        order_clear.clicked.connect(self.clear_orderby_metric)
        order_btn.clicked.connect(partial(self.update_orderby_metric, order_entry))
        order_null.clicked.connect(self.update_orderby_usenull)
        order_row.addWidget(order_label)
        order_row.addWidget(order_clear)
        order_row.addWidget(order_entry)
        order_row.addWidget(order_btn)
        order_row.addWidget(order_null)
        order_container = QtWidgets.QWidget()
        order_container.setLayout(order_row)
        option_layout.addWidget(order_container)

        sort_row = QtWidgets.QHBoxLayout()
        sort_label = QtWidgets.QLabel("Sort by")
        sort_combo = QtWidgets.QComboBox()
        sort_combo.addItems(SORT_METRIC_OPTIONS)
        sort_combo.setCurrentText(self.sort_metric_option)
        sort_btn = QtWidgets.QPushButton("+")
        sort_btn.clicked.connect(partial(self.update_sort_metric, sort_combo))
        sort_row.addWidget(sort_label)
        sort_row.addWidget(sort_combo)
        sort_row.addWidget(sort_btn)
        sort_container = QtWidgets.QWidget()
        sort_container.setLayout(sort_row)
        option_layout.addWidget(sort_container)

        search_row = QtWidgets.QHBoxLayout()
        search_label = QtWidgets.QLabel("Search")
        search_entry = QtWidgets.QLineEdit()
        search_btn = QtWidgets.QPushButton("~")
        search_btn.clicked.connect(partial(self.search_for_page, search_entry))
        search_row.addWidget(search_label)
        search_row.addWidget(search_entry)
        search_row.addWidget(search_btn)
        search_container = QtWidgets.QWidget()
        search_container.setLayout(search_row)
        option_layout.addWidget(search_container)

        goto_row = QtWidgets.QHBoxLayout()
        goto_label = QtWidgets.QLabel("Go to")
        goto_entry = QtWidgets.QLineEdit()
        goto_btn = QtWidgets.QPushButton("~")
        goto_btn.clicked.connect(partial(self.goto_page, goto_entry))
        goto_row.addWidget(goto_label)
        goto_row.addWidget(goto_entry)
        goto_row.addWidget(goto_btn)
        goto_container = QtWidgets.QWidget()
        goto_container.setLayout(goto_row)
        option_layout.addWidget(goto_container)

        modify_btn = QtWidgets.QPushButton("Modify mode")
        modify_btn.clicked.connect(self.complete_modify_mode)
        modify_btn.setStyleSheet("color: #ff6666;" if self.modify_mode else "")
        option_layout.addWidget(modify_btn)
        self.modify_mode_button = modify_btn

        thumb_btn = QtWidgets.QPushButton("Thumbnail mode")
        thumb_btn.clicked.connect(self.toggle_thumbnail_mode)
        thumb_btn.setStyleSheet("color: #ff6666;" if self.thumbnail_mode else "")
        option_layout.addWidget(thumb_btn)
        self.thumbnail_mode_button = thumb_btn

        self.tag_scroll_layout.addWidget(option_frame)

        state_items = []
        filetype_items = []
        label_items = []
        other_items = []

        for k, v in sorted(self.chosen_tags.items()):
            tag_name, tag_value = k
            tag_style = v
            if tag_style == "state":
                state_items.append((k, v))
            elif tag_style == "filetype":
                filetype_items.append((k, v))
            elif tag_style == "label":
                label_items.append((k, v))
            else:
                other_items.append((k, v))

        items = (
            state_items
            + filetype_items
            + label_items
            + other_items
            + [(("", ""), TagConditions.Is.value)]
        )

        for tag_name, tag_value in [i[0] for i in items]:
            row = QtWidgets.QWidget()
            row_layout = QtWidgets.QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(4)

            name_entry = QtWidgets.QLineEdit()
            name_entry.setText(tag_name)
            style_combo = QtWidgets.QComboBox()
            style_combo.addItems(TAG_STYLE_OPTIONS)
            style_combo.setCurrentText(
                self.chosen_tags.get((tag_name, tag_value), TagConditions.Is.value)
            )
            value_entry = QtWidgets.QLineEdit()
            value_entry.setText(tag_value)
            update_btn = QtWidgets.QPushButton("+")
            delete_btn = QtWidgets.QPushButton("x")

            update_btn.clicked.connect(
                partial(
                    self.update_tag,
                    name_entry=name_entry,
                    style_combo=style_combo,
                    value_entry=value_entry,
                    old_name=tag_name,
                    old_value=tag_value,
                )
            )
            delete_btn.clicked.connect(
                partial(self.delete_tag, old_name=tag_name, old_value=tag_value)
            )

            row_layout.addWidget(name_entry, 1)
            row_layout.addWidget(style_combo, 0)
            row_layout.addWidget(value_entry, 1)
            row_layout.addWidget(update_btn, 0)
            row_layout.addWidget(delete_btn, 0)

            self.tag_scroll_layout.addWidget(row)

        self.tag_scroll_layout.addStretch(1)

    def update_tag(self, name_entry, style_combo, value_entry, old_name, old_value):
        new_name = name_entry.text().strip().lower()
        new_style = style_combo.currentText()
        new_value = value_entry.text().strip().lower()

        if new_name == "" and new_value == "":
            self.delete_tag(old_name, old_value)
        else:
            if not (old_name == "" and old_value == ""):
                if (old_name, old_value) in self.chosen_tags:
                    self.chosen_tags.pop((old_name, old_value))
            self.chosen_tags[(new_name, new_value)] = new_style
            self.rebuild_and_reset()

    def delete_tag(self, old_name, old_value):
        if old_name == "" and old_value == "":
            return
        self.chosen_tags.pop((old_name, old_value))
        self.rebuild_and_reset()

    def update_items_per_bin(self, entry):
        if entry.text().isnumeric():
            value = int(entry.text())
            value = max(0, value)
        else:
            value = 0
        self.items_per_bin = value
        self.rebuild_and_reset()

    def modify_items_per_bin(self, change):
        self.items_per_bin = max(0, self.items_per_bin + change)
        self.rebuild_and_reset()

    def update_items_per_window(self, entry):
        if entry.text().isnumeric():
            value = int(entry.text())
            value = max(1, value)
        else:
            value = 1
        self.items_per_window = value
        self.rebuild_and_reset()

    def modify_items_per_window(self, change):
        self.items_per_window = max(1, self.items_per_window + change)
        self.rebuild_and_reset()

    def update_page_increment(self, entry):
        if entry.text().isnumeric():
            value = int(entry.text())
            value = max(1, value)
        else:
            value = 1
        self.page_increment_rate = value
        self.rebuild_and_reset()

    def update_video_bin_count(self, entry):
        if entry.text().isnumeric():
            value = int(entry.text())
            value = max(0, value)
        else:
            value = 1
        self.max_bin_videos = value
        self.rebuild_and_reset()

    def update_videos_currently_played(self, entry):
        if entry.text().isnumeric():
            value = int(entry.text())
            value = max(0, value)
        else:
            value = 0
        self.videos_currently_played = value
        self.rebuild_and_reset()

    def modify_page_increment(self, change):
        self.page_increment_rate = max(1, self.page_increment_rate + change)
        self.rebuild_and_reset()

    def modify_video_bin_count(self, change):
        self.max_bin_videos = max(0, self.max_bin_videos + change)
        self.rebuild_and_reset()

    def modify_videos_currently_played(self, change):
        self.videos_currently_played = max(0, self.videos_currently_played + change)
        self.rebuild_and_reset()

    def update_bin_group_metric(self, entry):
        self.bin_group_metric = entry.text()
        self.rebuild_and_reset()

    def remove_bin_group_metric(self):
        self.bin_group_metric = ""
        self.rebuild_and_reset()

    def update_sort_metric(self, sort_combo):
        self.sort_metric_option = sort_combo.currentText()
        self.rebuild_and_reset()

    def update_orderby_metric(self, entry):
        value = entry.text().strip().lower()
        if value == self.orderby_metric:
            return
        self.orderby_metric = value if value else "id"
        self.rebuild_and_reset()

    def clear_orderby_metric(self):
        self.orderby_metric = "id"
        self.rebuild_and_reset()

    def update_orderby_usenull(self):
        self.orderby_usenull = not self.orderby_usenull
        self.rebuild_and_reset()

    def clear_item_id_inplace(self, item_id, onclear, item_type):
        video_widget = self.id_data[item_id].get("video_widget")
        if video_widget:
            video_widget.close()
            self.id_data[item_id].pop("video_widget", None)

        relevant_bin = self.id_data[item_id]["bin"]
        width = self.id_data[item_id]["width"]
        relevant_bin["ids"].remove(item_id)
        relevant_bin["width"] -= width

        if len(relevant_bin["ids"]) == 0:
            metric = self.id_data[item_id]["metric"]
            for i, z in enumerate(self.page_data):
                _, _, b = z
                if b == relevant_bin:
                    self.page_data.pop(i)
                    break
            self.bins[metric].remove(relevant_bin)
            if len(self.bins[metric]) == 0:
                self.bins.pop(metric)

        self.item_ids.remove(item_id)
        self.id_data.pop(item_id)
        self.reset_items()

        if item_type == FileType.Image or self.thumbnail_mode:
            onclear()

    def delete_id(self, item_id):
        if self.modify_mode:
            item_type = Item.objects.get(id=item_id).filetype
            self.clear_item_id_inplace(
                item_id, onclear=partial(delete_items, {item_id}), item_type=item_type
            )

    def modify_id(self, item_id):
        if self.modify_mode:
            filetype = Item.objects.get(id=item_id).filetype
            if filetype == int(FileType.Video):
                return
            self.clear_item_id_inplace(
                item_id,
                item_type=filetype,
                onclear=partial(edit_item, item_id, new_state=FileState.NeedsModify),
            )

    def label_id(self, item_id):
        if self.modify_mode:
            self.clear_item_id_inplace(
                item_id,
                item_type=Item.objects.get(id=item_id).filetype,
                onclear=partial(edit_item, item_id, new_state=FileState.NeedsLabel),
            )

    def tag_id(self, item_id):
        if self.modify_mode:
            edit_item(item_id, new_state=FileState.NeedsTags)

    def open_id(self, item_id):
        path = Item.objects.get(id=item_id).getpath()
        os.startfile(path)

    def complete_modify_mode(self):
        self.modify_mode = not self.modify_mode
        self.modify_mode_button.setStyleSheet(
            "color: #ff6666;" if self.modify_mode else ""
        )
        self.load_items()

    def toggle_thumbnail_mode(self):
        self.thumbnail_mode = not self.thumbnail_mode
        self.thumbnail_mode_button.setStyleSheet(
            "color: #ff6666;" if self.thumbnail_mode else ""
        )
        self.reset_items()

    def reset_items(self):
        self.load_items()

    def reset_all(self):
        self.load_chosen_tags()
        self.load_items()

    def rebuild_and_reset(self):
        self.get_ids_and_build_bins()
        self.reset_all()

    def random_page(self):
        if self.max_page <= self.items_per_window:
            self.current_page = 0
        else:
            self.current_page = random.randint(0, self.max_page - self.items_per_window)
        self.load_items()

    def decrement_page(self):
        self.current_page = max(self.current_page - self.page_increment_rate, 0)
        self.load_items()

    def increment_page(self):
        self.current_page = min(
            self.current_page + self.page_increment_rate,
            self.max_page - self.items_per_window,
        )
        self.load_items()

    def decrement_page_person(self):
        current_metric = self.page_data[self.current_page][0]
        for r in range(self.current_page - 1, -1, -1):
            metric = self.page_data[r][0]
            self.current_page = r
            if metric != current_metric:
                break
        self.reset_items()

    def increment_page_person(self):
        current_metric = self.page_data[self.current_page][0]
        for r in range(self.current_page, self.max_page - self.items_per_window + 1):
            metric = self.page_data[r][0]
            self.current_page = r
            if metric != current_metric:
                break
        self.reset_items()

    def search_for_page(self, entry):
        metric_value = entry.text()
        found_startswith = False
        for i in range(self.max_page - self.items_per_window + 1):
            metric = self.page_data[i][0]
            if metric.startswith(metric_value) and not found_startswith:
                self.current_page = i
                found_startswith = True
            if metric == metric_value:
                self.current_page = i
                break
        self.reset_items()

    def goto_page(self, entry):
        if not entry.text().isdigit():
            return
        value = int(entry.text())
        self.current_page = min(value, self.max_page - self.items_per_window)
        self.current_page = max(self.current_page, 0)
        self.reset_items()

    def closeEvent(self, event):
        self.clear_video_players()
        if not self.completed:
            self.window_closed_manually = True
        super().closeEvent(event)

    def wheelEvent(self, event):
        if event.angleDelta().y() < 0:
            self.increment_page()
        elif event.angleDelta().y() > 0:
            self.decrement_page()
        event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_page_dimensions()
        self.reset_items()


def start_view_application():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)
    window = ViewApplication()
    window.showMaximized()
    window.raise_()
    window.activateWindow()
    app.exec()
    return not window.window_closed_manually, window.completed


if __name__ == "__main__":
    start_view_application()
