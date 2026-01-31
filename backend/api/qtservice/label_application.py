from api.views_extension import (
    get_top_x_unlabelled_ids,
    get_all_labels,
    get_thumbnail,
    edit_item,
)
from api.models import FileState
from functools import partial
import sys

from PIL import Image, ImageQt
from PySide6 import QtCore, QtGui, QtWidgets


DEFAULT_CARD_PADDING = 8
THUMBNAIL_BG = (28, 29, 33)
TOTAL_ITEMS = 60


class LabelApplication(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.window_closed_manually = False
        self.completed = False

        self.selected_ids = set()
        self.id_data = {}
        self.ids = []
        self.labels = []
        self.label_input = ""

        self.setWindowTitle("Label application")
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
        self.load_next_items()

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

        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.scroll_contents = QtWidgets.QWidget()
        self.scroll_layout = QtWidgets.QGridLayout(self.scroll_contents)
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_layout.setSpacing(6)
        self.scroll_area.setWidget(self.scroll_contents)

        left_layout.addLayout(select_layout)
        left_layout.addWidget(self.scroll_area, 1)

        # Right panel
        right_panel = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        enter_label = QtWidgets.QLabel("Enter label")
        enter_label.setStyleSheet("font-weight: bold;")
        self.entry_bar = QtWidgets.QLineEdit()
        self.entry_bar.textChanged.connect(self.on_entry_change)

        self.results_container = QtWidgets.QWidget()
        self.results_layout = QtWidgets.QVBoxLayout(self.results_container)
        self.results_layout.setContentsMargins(0, 0, 0, 0)
        self.results_layout.setSpacing(4)

        right_layout.addWidget(enter_label)
        right_layout.addWidget(self.entry_bar)
        right_layout.addWidget(self.results_container, 1)

        layout.addWidget(left_panel, 4)
        layout.addWidget(right_panel, 1)

        self.select_all_button.clicked.connect(self.select_all)
        self.deselect_all_button.clicked.connect(self.deselect_all)

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

    def load_next_items(self):
        self.ids = get_top_x_unlabelled_ids(TOTAL_ITEMS)
        self.labels = [
            item["label"] for item in get_all_labels() if item["label"] != ""
        ]
        self.labels.sort()

        if not self.ids:
            self.completed = True
            self.close()
            return

        for item_id in self.ids:
            if item_id in self.id_data:
                continue
            self.id_data[item_id] = {
                "selected": False,
                "batch_toggled": False,
            }

        self.load_images()
        self._scroll_to_top()
        self.on_entry_change()

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

    def load_images(self):
        while self.scroll_layout.count():
            item = self.scroll_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        if not self.ids:
            return

        first_thumb = thumbnail_cache[self.ids[0]]
        target_side = max(first_thumb.width, first_thumb.height)
        columns = self._compute_columns(target_side)

        row = 0
        col = 0

        for i, item_id in enumerate(self.ids):
            frame = QtWidgets.QFrame()
            frame_layout = QtWidgets.QVBoxLayout(frame)
            frame_layout.setContentsMargins(4, 4, 4, 4)
            frame_layout.setSpacing(4)

            thumbnail = thumbnail_cache[item_id]
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
            frame_layout.setAlignment(QtCore.Qt.AlignTop | QtCore.Qt.AlignHCenter)
            frame_layout.addWidget(image_label, 0, QtCore.Qt.AlignHCenter)
            frame_layout.addWidget(controls_container, 0, QtCore.Qt.AlignHCenter)

            self.scroll_layout.addWidget(frame, row, col)
            col += 1
            if col >= columns:
                row += 1
                col = 0

        if len(self.ids) == 1:
            item_id = self.ids[0]
            self.id_data[item_id]["selected"] = True
            self.selected_ids.add(item_id)

            button = self.id_data[item_id]["buttons"]["check"]
            self._set_select_button_style(button, self.id_data[item_id]["selected"])

    def _scroll_to_top(self):
        if self.scroll_area and self.scroll_area.verticalScrollBar():
            self.scroll_area.verticalScrollBar().setValue(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.ids:
            self._resize_timer.start(150)

    def select_item(self, item_id):
        selected = self.id_data[item_id]["selected"]
        if selected:
            self.selected_ids.remove(item_id)
            self.id_data[item_id]["selected"] = False
        else:
            self.selected_ids.add(item_id)
            self.id_data[item_id]["selected"] = True

        button = self.id_data[item_id]["buttons"]["check"]
        self._set_select_button_style(button, self.id_data[item_id]["selected"])

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

        button = self.id_data[item_id]["buttons"]["batch"]
        self._set_batch_button_style(button, self.id_data[item_id]["batch_toggled"])

    def select_all(self):
        for item_id in self.ids:
            self.id_data[item_id]["selected"] = True
            self.id_data[item_id]["batch_toggled"] = False
            self._set_select_button_style(
                self.id_data[item_id]["buttons"]["check"], True
            )
            self._set_batch_button_style(
                self.id_data[item_id]["buttons"]["batch"], False
            )
            self.selected_ids.add(item_id)

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

    def on_entry_change(self, *args):
        while self.results_layout.count():
            item = self.results_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        user_input = self.entry_bar.text().strip()
        self.label_input = user_input
        result_labels = []

        for label in self.labels:
            if label.startswith(user_input):
                result_labels.append(label)
            if len(result_labels) == 10:
                break

        for label in result_labels:
            row = QtWidgets.QHBoxLayout()
            label_widget = QtWidgets.QLabel(label)
            apply_button = QtWidgets.QPushButton("+")
            apply_button.clicked.connect(partial(self.modify_items, label))
            row.addWidget(label_widget, 1)
            row.addWidget(apply_button, 0)
            container = QtWidgets.QWidget()
            container.setLayout(row)
            self.results_layout.addWidget(container)

        if user_input and user_input not in result_labels:
            row = QtWidgets.QHBoxLayout()
            label_widget = QtWidgets.QLabel(user_input)
            apply_button = QtWidgets.QPushButton("+")
            apply_button.clicked.connect(partial(self.modify_items, user_input))
            row.addWidget(label_widget, 1)
            row.addWidget(apply_button, 0)
            container = QtWidgets.QWidget()
            container.setLayout(row)
            self.results_layout.addWidget(container)

        self.results_layout.addStretch(1)

    def modify_items(self, label):
        if label == "":
            return
        for item_id in list(self.selected_ids):
            edit_item(
                item_id=item_id, new_label=label, new_state=int(FileState.NeedsClip)
            )
            self.id_data.pop(item_id, None)

        self.selected_ids = set()
        self.entry_bar.clear()
        self.label_input = ""

        if label not in self.labels:
            self.labels.append(label)
            self.labels.sort()

        self.load_next_items()

    def closeEvent(self, event):
        if not self.completed:
            self.window_closed_manually = True
        super().closeEvent(event)


def start_label_application():
    if not get_top_x_unlabelled_ids(1):
        return True, True
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)
    window = LabelApplication()
    if window.completed:
        return not window.window_closed_manually, window.completed
    window.showMaximized()
    window.raise_()
    window.activateWindow()
    app.exec()
    return not window.window_closed_manually, window.completed


if __name__ == "__main__":
    start_label_application()
