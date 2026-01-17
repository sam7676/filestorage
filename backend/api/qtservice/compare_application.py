from api.views_extension import (
    get_random_compare_item,
    get_comparison_items,
    get_thumbnail,
    delete_items,
)
from api.models import Item, FileType
from functools import partial
import sys
import os

from PIL import Image, ImageQt
from PySide6 import QtCore, QtGui, QtWidgets


class CompareApplication(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.window_closed_manually = False
        self.completed = False

        self.item = None
        self.comparison_item_ids = []

        self.setWindowTitle("Compare")
        screen = QtGui.QGuiApplication.primaryScreen()
        if screen:
            geometry = screen.availableGeometry()
            width = int(geometry.width() * 0.85)
            height = int(geometry.height() * 0.85)
            self.resize(width, height)
            self.max_height_in_crop = int(geometry.height() * 0.7)
            self.max_width_of_crop = int(geometry.width() * 0.5)
        else:
            self.resize(1500, 900)
            self.max_height_in_crop = 760
            self.max_width_of_crop = 900

        self._build_ui()
        self._apply_dark_theme()
        self._resize_timer = QtCore.QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self.load_items)
        self.load_next_item()

    def _build_ui(self):
        root = QtWidgets.QWidget(self)
        self.setCentralWidget(root)

        layout = QtWidgets.QVBoxLayout(root)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.scroll_contents = QtWidgets.QWidget()
        self.scroll_layout = QtWidgets.QHBoxLayout(self.scroll_contents)
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_layout.setSpacing(0)
        self.scroll_area.setWidget(self.scroll_contents)
        self.scroll_contents.setStyleSheet("background-color: #1C1D21;")

        self.next_button = QtWidgets.QPushButton("Next")
        self.next_button.setMinimumHeight(48)
        self.next_button.clicked.connect(self.next)

        layout.addWidget(self.scroll_area, 1)
        next_row = QtWidgets.QHBoxLayout()
        next_row.addStretch(1)
        next_row.addWidget(self.next_button)
        next_row.addStretch(1)
        layout.addLayout(next_row, 0)

        QtGui.QShortcut(QtGui.QKeySequence("Return"), self, activated=self.next)

    def _apply_dark_theme(self):
        self.setStyleSheet(
            """
            QMainWindow { background-color: #1C1D21; color: #E6E6E6; }
            QWidget { background-color: #1C1D21; color: #E6E6E6; }
            QPushButton {
                background-color: #2B2E35;
                border: 1px solid #3A3D44;
                padding: 4px 8px;
            }
            """
        )

    def load_next_item(self):
        self.item = get_random_compare_item()
        if not self.item:
            self.completed = True
            self.close()
            return

        self.comparison_item_ids = get_comparison_items(self.item.id, 30)
        self.load_items()

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _pad_thumbnail(self, thumbnail, target_width, target_height):
        if thumbnail.height > target_height:
            scale = target_height / thumbnail.height
            resample = getattr(Image, "Resampling", Image).LANCZOS
            new_size = (
                max(1, int(thumbnail.width * scale)),
                max(1, int(thumbnail.height * scale)),
            )
            thumbnail = thumbnail.resize(new_size, resample=resample)
        canvas = Image.new("RGB", (target_width, target_height), (28, 29, 33))
        y = max(0, (target_height - thumbnail.height) // 2)
        canvas.paste(thumbnail, (0, y))
        return canvas

    def _build_card(self, item_id, is_main=False, max_width=None):
        item = Item.objects.filter(id=item_id).get()
        width_cap = self.max_width_of_crop if max_width is None else max_width
        max_height = self.max_height_in_crop
        new_width = max(1, int(width_cap))
        new_height = max(1, int(item.height * new_width / item.width))
        if new_height > max_height:
            new_height = max(1, int(max_height))
            new_width = max(1, int(item.width * new_height / item.height))

        if item.filetype == int(FileType.Image):
            resized_image = get_thumbnail(item.id, new_width, new_height)
        else:
            resized_image = get_thumbnail(item.id, new_width, new_height)

        resized_image = self._pad_thumbnail(
            resized_image, new_width, self.max_height_in_crop
        )

        qimage = ImageQt.ImageQt(resized_image)
        pixmap = QtGui.QPixmap.fromImage(qimage)

        card = QtWidgets.QFrame()
        card.setFrameShape(QtWidgets.QFrame.NoFrame)
        card_layout = QtWidgets.QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        image_button = QtWidgets.QPushButton()
        image_button.setIcon(QtGui.QIcon(pixmap))
        image_button.setIconSize(pixmap.size())
        image_button.clicked.connect(partial(self.open_item, item_id))
        image_button.setFlat(True)
        image_button.setStyleSheet(
            "border: none; background-color: #1C1D21; padding: 0; margin: 0;"
        )
        image_button.setSizePolicy(
            QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed
        )
        image_button.setFixedSize(pixmap.size())

        image_container = QtWidgets.QWidget()
        image_container_layout = QtWidgets.QVBoxLayout(image_container)
        image_container_layout.setContentsMargins(0, 0, 0, 0)
        image_container_layout.addStretch(1)
        image_container_layout.addWidget(
            image_button, 0, QtCore.Qt.AlignHCenter | QtCore.Qt.AlignVCenter
        )
        image_container_layout.addStretch(1)
        image_container.setFixedHeight(self.max_height_in_crop)
        image_container.setSizePolicy(
            QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Fixed
        )

        remove_button = QtWidgets.QPushButton(f"{item_id} X")
        remove_button.clicked.connect(partial(self.remove_item, item_id))
        remove_button.setFlat(True)
        remove_button.setStyleSheet(
            "border: none; padding: 0; margin: 0; color: #000000; background-color: #FFFFFF;"
            if not is_main
            else "border: none; padding: 0; margin: 0; color: #2EA8FF; background-color: #FFFFFF;"
        )
        remove_button.setSizePolicy(
            QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Fixed
        )

        card_layout.addWidget(
            image_container, 1, QtCore.Qt.AlignHCenter | QtCore.Qt.AlignVCenter
        )
        card_layout.addWidget(
            remove_button, 0, QtCore.Qt.AlignHCenter | QtCore.Qt.AlignBottom
        )

        return card

    def load_items(self):
        self._clear_layout(self.scroll_layout)

        viewport_width = self.scroll_area.viewport().width()
        spacing = self.scroll_layout.spacing()
        if viewport_width <= 0:
            QtCore.QTimer.singleShot(0, self.load_items)
            return

        main_width = 0
        if self.item:
            main_width = min(
                int(round(self.item.width * self.max_height_in_crop / self.item.height)),
                self.max_width_of_crop,
            )
            self.scroll_layout.addWidget(
                self._build_card(self.item.id, is_main=True, max_width=main_width)
            )

        available = max(0, viewport_width - main_width - spacing)
        card_width = self.max_width_of_crop
        full_items = 0
        if card_width + spacing > 0:
            full_items = available // (card_width + spacing)

        visible_ids = self.comparison_item_ids[: full_items + 1]
        for index, item_id in enumerate(visible_ids):
            max_width = card_width
            if index == len(visible_ids) - 1:
                remaining = available - full_items * (card_width + spacing)
                if remaining > 0:
                    max_width = min(card_width, remaining)
            self.scroll_layout.addWidget(self._build_card(item_id, max_width=max_width))

        # No stretch to keep cards adjacent

    def remove_item(self, item_id):
        if self.item and item_id == self.item.id:
            delete_items({item_id})
            self.load_next_item()
            return

        delete_items({item_id})
        self.comparison_item_ids = [
            iid for iid in self.comparison_item_ids if iid != item_id
        ]
        self.load_items()

    def next(self):
        self.load_next_item()

    def open_item(self, item_id):
        os.startfile(Item.objects.filter(id=item_id).get().getpath())

    def closeEvent(self, event):
        if not self.completed:
            self.window_closed_manually = True
        super().closeEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        viewport = self.scroll_area.viewport()
        if viewport:
            self.max_height_in_crop = max(1, int(viewport.height() * 0.4))
            self.max_width_of_crop = max(1, int(viewport.width() * 0.4))
        if self.item:
            self._resize_timer.start(100)


def start_compare_application():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)
    window = CompareApplication()
    window.showMaximized()
    window.raise_()
    window.activateWindow()
    app.exec()
    return not window.window_closed_manually, window.completed


if __name__ == "__main__":
    start_compare_application()
