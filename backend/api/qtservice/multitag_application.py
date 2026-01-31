from api.views_extension import (
    check_for_crops,
    check_for_modify,
    check_for_unlabelled,
    get_all_labels,
    get_distinct_tags,
    get_untagged_ids,
    TAG_STYLE_OPTIONS,
    get_thumbnail,
    add_tags,
    thumbnail_cache,
)
from api.models import Item, TagConditions
from functools import partial
import math
import sys
import os

from PIL import Image, ImageQt
from PySide6 import QtCore, QtGui, QtWidgets


DEFAULT_CARD_PADDING = 8
THUMBNAIL_BG = (28, 29, 33)
ITEMS_PER_PAGE = 100
FAST_ITEMS_PER_PAGE = 10


        
        

class MultiTagApplication(QtWidgets.QMainWindow):
    def __init__(self, tag_names=None):
        super().__init__()
        self.window_closed_manually = False
        self.completed = False

        self.tag_names = list(tag_names or [""])
        self.tag_name = ""
        self.ids = []
        self.ids_set = set()
        self.page = 0
        self.max_page = 0
        self.items_per_page = ITEMS_PER_PAGE if tag_names is not None else FAST_ITEMS_PER_PAGE
        self.selected_ids = set()
        self.id_data = {}
        self.chosen_tags = {}
        self.labels = []
        self.tag_values = []
        self.tag_value_input = ""

        self.setWindowTitle("Multitag application")
        screen = QtGui.QGuiApplication.primaryScreen()
        if screen:
            geometry = screen.availableGeometry()
            width = int(geometry.width() * 0.85)
            height = int(geometry.height() * 0.85)
            self.resize(width, height)
        else:
            self.resize(1500, 900)

        self._build_ui()
        self._apply_dark_theme()
        self._resize_timer = QtCore.QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self.load_images)
        self.load_next_tag()

    def _compute_columns(self, thumbnail_width):
        viewport_width = self.scroll_area.viewport().width()
        if viewport_width <= 0:
            return 1
        margins = self.scroll_layout.contentsMargins()
        available = viewport_width - (margins.left() + margins.right())
        spacing = self.scroll_layout.spacing()
        card_width = thumbnail_width + DEFAULT_CARD_PADDING
        if card_width <= 0:
            return 1
        return max(1, (available + spacing) // (card_width + spacing))

    def _pad_thumbnail(self, thumbnail, target_side):
        if thumbnail.width > target_side or thumbnail.height > target_side:
            scale = min(target_side / thumbnail.width, target_side / thumbnail.height)
            resample = getattr(Image, "Resampling", Image).LANCZOS
            new_size = (
                max(1, int(thumbnail.width * scale)),
                max(1, int(thumbnail.height * scale)),
            )
            thumbnail = thumbnail.resize(new_size, resample=resample)
        canvas = Image.new("RGB", (target_side, target_side), THUMBNAIL_BG)
        x = (target_side - thumbnail.width) // 2
        y = (target_side - thumbnail.height) // 2
        canvas.paste(thumbnail, (x, y))
        return canvas

    def _build_ui(self):
        root = QtWidgets.QWidget(self)
        self.setCentralWidget(root)

        layout = QtWidgets.QHBoxLayout(root)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Left panel
        left_panel = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        select_layout = QtWidgets.QHBoxLayout()
        self.select_all_button = QtWidgets.QPushButton("Select all")
        self.deselect_all_button = QtWidgets.QPushButton("Deselect all")
        select_layout.addWidget(self.select_all_button)
        select_layout.addWidget(self.deselect_all_button)

        page_layout = QtWidgets.QHBoxLayout()
        self.items_per_page_entry = QtWidgets.QLineEdit()
        self.items_per_page_entry.setFixedWidth(60)
        self.items_per_page_entry.setText(str(self.items_per_page))
        self.items_per_page_button = QtWidgets.QPushButton("Set")
        self.page_label = QtWidgets.QLabel("0 / 0")
        self.page_entry = QtWidgets.QLineEdit()
        self.page_entry.setFixedWidth(60)
        self.page_button = QtWidgets.QPushButton("Go")

        page_layout.addWidget(self.items_per_page_entry)
        page_layout.addWidget(self.items_per_page_button)
        page_layout.addWidget(self.page_label)
        page_layout.addWidget(self.page_entry)
        page_layout.addWidget(self.page_button)

        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.scroll_contents = QtWidgets.QWidget()
        self.scroll_layout = QtWidgets.QGridLayout(self.scroll_contents)
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_layout.setSpacing(6)
        self.scroll_area.setWidget(self.scroll_contents)

        left_layout.addLayout(select_layout)
        left_layout.addLayout(page_layout)
        left_layout.addWidget(self.scroll_area, 1)

        # Right panel
        right_panel = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        tag_name_label = QtWidgets.QLabel("Tag name")
        self.tag_name_entry = QtWidgets.QLineEdit()
        self.tag_name_button = QtWidgets.QPushButton("Set")

        tag_value_label = QtWidgets.QLabel("Tag value")
        self.tag_value_entry = QtWidgets.QLineEdit()
        self.tag_value_button = QtWidgets.QPushButton("Add")
        self.tag_value_entry.textChanged.connect(self.on_tag_value_change)

        suggested_label = QtWidgets.QLabel("Suggested values")
        suggested_label.setStyleSheet("font-weight: bold;")
        self.results_container = QtWidgets.QWidget()
        self.results_layout = QtWidgets.QVBoxLayout(self.results_container)
        self.results_layout.setContentsMargins(0, 0, 0, 0)
        self.results_layout.setSpacing(4)

        right_layout.addWidget(tag_name_label)
        right_layout.addWidget(self.tag_name_entry)
        right_layout.addWidget(self.tag_name_button)
        right_layout.addWidget(tag_value_label)
        right_layout.addWidget(self.tag_value_entry)
        right_layout.addWidget(self.tag_value_button)
        right_layout.addWidget(suggested_label)
        right_layout.addWidget(self.results_container, 1)

        self.tags_scroll = QtWidgets.QScrollArea()
        self.tags_scroll.setWidgetResizable(True)
        self.tags_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.tags_scroll_contents = QtWidgets.QWidget()
        self.tags_layout = QtWidgets.QVBoxLayout(self.tags_scroll_contents)
        self.tags_layout.setContentsMargins(0, 0, 0, 0)
        self.tags_layout.setSpacing(4)
        self.tags_scroll.setWidget(self.tags_scroll_contents)

        right_layout.addWidget(self.tags_scroll, 2)

        layout.addWidget(left_panel, 4)
        layout.addWidget(right_panel, 1)

        self.select_all_button.clicked.connect(self.select_all)
        self.deselect_all_button.clicked.connect(self.deselect_all)
        self.items_per_page_button.clicked.connect(self.update_items_per_page)
        self.page_button.clicked.connect(self.update_page)
        self.tag_name_button.clicked.connect(self.edit_tagname)
        self.tag_value_button.clicked.connect(partial(self.add_tags_to_selected, None)) # Qt calls with the argument False seemingly

        QtGui.QShortcut(QtGui.QKeySequence("Up"), self, activated=self.decrement_page)
        QtGui.QShortcut(QtGui.QKeySequence("Down"), self, activated=self.increment_page)
        QtGui.QShortcut(QtGui.QKeySequence("Left"), self, activated=self.decrement_page)
        QtGui.QShortcut(
            QtGui.QKeySequence("Right"), self, activated=self.increment_page
        )

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
            """
        )

    def load_next_tag(self):
        if not self.tag_names:
            self.completed = True
            self.close()
            return

        if any((check_for_crops(), check_for_modify(), check_for_unlabelled())):
            self.completed = True
            self.close()
            return

        self.selected_ids = set()
        self.id_data = {}
        self.chosen_tags = {}
        self.tag_name = self.tag_names.pop(0)
        self.tag_name_entry.setText(self.tag_name)

        self.load_ids()

    def load_ids(self):
        self.ids = list(get_untagged_ids(self.tag_name, self.chosen_tags))
        self.ids_set = set(self.ids)
        self.page = 0
        self.max_page = (
            math.ceil(len(self.ids) / self.items_per_page) if self.ids else 0
        )

        self.labels = [
            item["label"] for item in get_all_labels() if item["label"] != ""
        ]
        self.labels.sort()
        self._load_tag_values()

        if not self.ids:
            self.load_next_tag()
            return

        for item_id in self.ids:
            if item_id in self.id_data:
                continue
            self.id_data[item_id] = {
                "selected": False,
                "batch_toggled": False,
            }

        self.load_images()
        self.load_tags()
        self.on_tag_value_change()

    def load_images(self):
        while self.scroll_layout.count():
            item = self.scroll_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        ids = self.ids[
            self.items_per_page * self.page : self.items_per_page * (self.page + 1)
        ]
        self.ids_set = set(ids)
        if not ids:
            self.page_label.setText("0 / 0")
            return

        first_thumb = thumbnail_cache[ids[0]]
        target_side = max(first_thumb.width, first_thumb.height)
        columns = self._compute_columns(target_side)

        row = 0
        col = 0
        
        if len(self.ids) == 1:
            item_id = self.ids[0]
            self.id_data[item_id]["selected"] = True
            self.selected_ids.add(item_id)

        for i, item_id in enumerate(ids):
            card = QtWidgets.QFrame()
            card_layout = QtWidgets.QVBoxLayout(card)
            card_layout.setContentsMargins(4, 4, 4, 4)
            card_layout.setSpacing(4)
            

            thumbnail = first_thumb if i == 0 else thumbnail_cache[item_id]

            thumbnail = self._pad_thumbnail(thumbnail, target_side)
            qimage = ImageQt.ImageQt(thumbnail)
            pixmap = QtGui.QPixmap.fromImage(qimage)
            pixmap = pixmap.scaled(
                target_side,
                target_side,
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation,
            )
            image_label = QtWidgets.QLabel(alignment=QtCore.Qt.AlignCenter)
            image_label.setPixmap(pixmap)
            image_label.setStyleSheet("background-color: #1C1D21;")

            controls_container = QtWidgets.QWidget()
            controls = QtWidgets.QHBoxLayout(controls_container)
            controls.setContentsMargins(0, 0, 0, 0)
            controls.setSpacing(4)
            batch_button = QtWidgets.QPushButton("Batch")
            select_button = QtWidgets.QPushButton("Select")
            self._set_batch_button_style(batch_button, self.id_data[item_id]["batch_toggled"])
            self._set_select_button_style(select_button, self.id_data[item_id]["selected"])
            
            id_label = QtWidgets.QLabel(str(item_id))
            id_label.setAlignment(QtCore.Qt.AlignCenter)

            batch_button.clicked.connect(partial(self.select_batch, item_id))
            select_button.clicked.connect(partial(self.select_item, item_id))

            self.id_data[item_id]["buttons"] = {
                "check": select_button,
                "batch": batch_button,
            }

            controls.addWidget(batch_button)
            controls.addWidget(id_label)
            controls.addWidget(select_button)

            if not pixmap.isNull():
                controls_container.setFixedWidth(pixmap.width())
            card_layout.setAlignment(QtCore.Qt.AlignTop | QtCore.Qt.AlignHCenter)
            card_layout.addWidget(image_label, 0, QtCore.Qt.AlignHCenter)
            card_layout.addWidget(controls_container, 0, QtCore.Qt.AlignHCenter)

            self.scroll_layout.addWidget(card, row, col)
            col += 1
            if col >= columns:
                row += 1
                col = 0

        self.page_label.setText(
            f"{self.page + 1} / {self.max_page}" if self.max_page else "0 / 0"
        )

    def load_tags(self):
        while self.tags_layout.count():
            item = self.tags_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

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

            update_button = QtWidgets.QPushButton("+")
            update_button.clicked.connect(
                partial(
                    self.update_tag,
                    name_entry=name_entry,
                    style_combo=style_combo,
                    value_entry=value_entry,
                    old_name=tag_name,
                    old_value=tag_value,
                )
            )
            delete_button = QtWidgets.QPushButton("x")
            delete_button.clicked.connect(
                partial(self.delete_tag, old_name=tag_name, old_value=tag_value)
            )

            row_layout.addWidget(name_entry, 1)
            row_layout.addWidget(style_combo, 0)
            row_layout.addWidget(value_entry, 1)
            row_layout.addWidget(update_button, 0)
            row_layout.addWidget(delete_button, 0)

            self.tags_layout.addWidget(row)

        self.tags_layout.addStretch(1)

    def _load_tag_values(self):
        if not self.tag_name:
            self.tag_values = []
            return
        values = []
        for name, value in get_distinct_tags():
            if name == self.tag_name and value != "":
                values.append(value)
        self.tag_values = sorted(set(values))

    def on_tag_value_change(self, *args):
        while self.results_layout.count():
            item = self.results_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        user_input = self.tag_value_entry.text().strip().lower()
        self.tag_value_input = user_input
        result_values = []

        for value in self.tag_values:
            if value.startswith(user_input):
                result_values.append(value)
            if len(result_values) == 10:
                break

        for value in result_values:
            row = QtWidgets.QHBoxLayout()
            value_widget = QtWidgets.QLabel(value)
            apply_button = QtWidgets.QPushButton("+")
            apply_button.clicked.connect(partial(self.add_tags_to_selected, value))
            row.addWidget(value_widget, 1)
            row.addWidget(apply_button, 0)
            container = QtWidgets.QWidget()
            container.setLayout(row)
            self.results_layout.addWidget(container)

        if user_input and user_input not in result_values:
            row = QtWidgets.QHBoxLayout()
            value_widget = QtWidgets.QLabel(user_input)
            apply_button = QtWidgets.QPushButton("+")
            apply_button.clicked.connect(partial(self.add_tags_to_selected, user_input))
            row.addWidget(value_widget, 1)
            row.addWidget(apply_button, 0)
            container = QtWidgets.QWidget()
            container.setLayout(row)
            self.results_layout.addWidget(container)

        self.results_layout.addStretch(1)

    def update_tag(self, name_entry, style_combo, value_entry, old_name, old_value):
        new_name = name_entry.text().strip().lower()
        new_style = style_combo.currentText()
        new_value = value_entry.text().strip().lower()

        if new_name == "" and new_value == "":
            self.delete_tag(old_name, old_value)
        else:
            if not (old_name == "" and old_value == ""):
                self.chosen_tags.pop((old_name, old_value), None)
            self.chosen_tags[(new_name, new_value)] = new_style
            self.reset()

    def delete_tag(self, old_name, old_value):
        if old_name == "" and old_value == "":
            return
        self.chosen_tags.pop((old_name, old_value), None)
        self.reset()

    def select_item(self, item_id):
        selected = self.id_data[item_id]["selected"]
        if selected:
            self.selected_ids.remove(item_id)
            self.id_data[item_id]["selected"] = False
        else:
            self.selected_ids.add(item_id)
            self.id_data[item_id]["selected"] = True
        self._set_select_button_style(
            self.id_data[item_id]["buttons"]["check"],
            self.id_data[item_id]["selected"],
        )

    def _set_select_button_style(self, button, selected):
        if selected:
            button.setStyleSheet(
                "background-color: #2D4F3A; border: 1px solid #3A3D44;"
            )
        else:
            button.setStyleSheet("")

    def _set_batch_button_style(self, button, toggled):
        if toggled:
            button.setStyleSheet(
                "background-color: #463A67; border: 1px solid #3A3D44;"
            )
        else:
            button.setStyleSheet("")

    def select_batch(self, item_id):
        self.id_data[item_id]["batch_toggled"] = not self.id_data[item_id][
            "batch_toggled"
        ]

        batch_diffs = []
        in_batch = []
        open_batch = False

        for iter_item_id in self.ids:
            if self.id_data[iter_item_id]["batch_toggled"]:
                batch_diffs.append(iter_item_id)

        if len(batch_diffs) >= 2:
            for iter_item_id in self.ids:
                if iter_item_id == batch_diffs[0]:
                    open_batch = True
                if open_batch:
                    in_batch.append(iter_item_id)
                if iter_item_id == batch_diffs[1]:
                    open_batch = False

            for iter_item_id in in_batch:
                self.id_data[iter_item_id]["batch_toggled"] = False
                self.id_data[iter_item_id]["selected"] = True
                self.selected_ids.add(iter_item_id)
                self._set_select_button_style(
                    self.id_data[iter_item_id]["buttons"]["check"], True
                )
                self._set_batch_button_style(
                    self.id_data[iter_item_id]["buttons"]["batch"], False
                )

        self._set_batch_button_style(
            self.id_data[item_id]["buttons"]["batch"],
            self.id_data[item_id]["batch_toggled"],
        )

    def select_all(self):
        for item_id in self.ids:
            self.id_data[item_id]["selected"] = True
            self.id_data[item_id]["batch_toggled"] = False
            self.selected_ids.add(item_id)
            
            if "buttons" in self.id_data[item_id]:
                self._set_select_button_style(
                    self.id_data[item_id]["buttons"]["check"], True
                )
                self._set_batch_button_style(
                    self.id_data[item_id]["buttons"]["batch"], False
                )


    def deselect_all(self):
        for item_id in self.ids:
            self.id_data[item_id]["selected"] = False
            self.id_data[item_id]["batch_toggled"] = False
            self._set_select_button_style(
                self.id_data[item_id]["buttons"]["check"], False
            )
            self._set_batch_button_style(
                self.id_data[item_id]["buttons"]["batch"], False
            )
        self.selected_ids = set()

    def add_tags_to_selected(self, value=None):
       
        
        if value is None:
            new_value = self.tag_value_entry.text().strip().lower()
        else:
            new_value = str(value).strip().lower()
        
         
        if new_value == "":
            return
        add_tags(
            {item_id: {self.tag_name: [new_value, ]} for item_id in self.selected_ids}
        )
        for item_id in self.selected_ids:
            self.id_data.pop(item_id, None)
        self.selected_ids = set()
        self.tag_value_entry.clear()
        if new_value and new_value not in self.tag_values:
            self.tag_values.append(new_value)
            self.tag_values.sort()
        self.on_tag_value_change()
        self.reset()

    def edit_tagname(self):
        new_name = self.tag_name_entry.text().strip().lower()
        if new_name:
            self.tag_name = new_name
            self._load_tag_values()
            self.on_tag_value_change()
            self.reset()

    def update_items_per_page(self):
        value = self.items_per_page_entry.text().strip()
        if value.isdigit():
            value = int(value)
            if value <= 0:
                return
            self.items_per_page = value
            self.reset()

    def update_page(self):
        value = self.page_entry.text().strip()
        if value.isdigit():
            value = int(value) - 1
            self.page = min(value, self.max_page - 1)
            self.page = max(0, self.page)
            self.page_entry.clear()
            self.load_images()
            self._scroll_to_top()

    def increment_page(self):
        self.page = min(self.page + 1, self.max_page - 1)
        self.load_images()
        self._scroll_to_top()

    def decrement_page(self):
        self.page = max(0, self.page - 1)
        self.load_images()
        self._scroll_to_top()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.ids_set:
            self._resize_timer.start(150)

    def open_items(self, item_ids):
        for item_id in item_ids:
            os.startfile(Item.objects.filter(id=item_id).get().getpath())

    def reset(self):
        self.load_ids()
        self._scroll_to_top()

    def closeEvent(self, event):
        if not self.completed:
            self.window_closed_manually = True
        super().closeEvent(event)

    def _scroll_to_top(self):
        if self.scroll_area and self.scroll_area.verticalScrollBar():
            self.scroll_area.verticalScrollBar().setValue(0)


def start_multitag_application(tag_names=None):
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)
    window = MultiTagApplication(tag_names=tag_names)
    if window.completed:
        return not window.window_closed_manually, window.completed
    window.showMaximized()
    window.raise_()
    window.activateWindow()
    app.exec()
    return not window.window_closed_manually, window.completed


if __name__ == "__main__":
    start_multitag_application()
