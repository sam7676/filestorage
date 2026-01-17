from api.views_extension import (
    get_top_x_needsmodify_ids,
    get_thumbnail,
    edit_item,
    delete_items,
    start_file,
)
from api.utils.process_images import crop_and_resize_image
from api.models import Item, FileState
from functools import partial
import sys
import os

from PIL import Image, ImageQt
from PySide6 import QtCore, QtGui, QtWidgets


DEFAULT_CARD_PADDING = 8
THUMBNAIL_BG = (28, 29, 33)


class ClickableLabel(QtWidgets.QLabel):
    def __init__(self, on_click, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._on_click = on_click

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self._on_click()
        super().mousePressEvent(event)


class ModifyApplication(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.window_closed_manually = False
        self.completed = False

        self.id_data = {}
        self.ids = []
        self.scrollbar_y_pos = 0

        self.setWindowTitle("Modify")
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

        layout = QtWidgets.QVBoxLayout(root)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.scroll_area.verticalScrollBar().valueChanged.connect(self._store_scroll)

        self.scroll_contents = QtWidgets.QWidget()
        self.scroll_layout = QtWidgets.QGridLayout(self.scroll_contents)
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_layout.setSpacing(6)
        self.scroll_area.setWidget(self.scroll_contents)

        self.refresh_button = QtWidgets.QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh_reset)

        layout.addWidget(self.scroll_area, 1)
        layout.addWidget(self.refresh_button, 0)

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
            QScrollArea { border: 1px solid #2C2E34; }
            """
        )

    def _store_scroll(self, value):
        self.scrollbar_y_pos = value

    def load_next_items(self):
        self.ids = get_top_x_needsmodify_ids(100)
        if not self.ids:
            self.completed = True
            self.close()
            return
        self.load_images()

    def load_images(self):
        while self.scroll_layout.count():
            item = self.scroll_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        if not self.ids:
            return

        first_thumb = get_thumbnail(self.ids[0])
        target_side = max(first_thumb.width, first_thumb.height)
        columns = self._compute_columns(target_side)

        ids_per_row = []
        row = 0
        col = 0

        for i, item_id in enumerate(self.ids):
            if col == 0:
                ids_per_row.append([])
            card = QtWidgets.QFrame()
            card_layout = QtWidgets.QVBoxLayout(card)
            card_layout.setContentsMargins(4, 4, 4, 4)
            card_layout.setSpacing(4)

            thumbnail = first_thumb if i == 0 else get_thumbnail(item_id)
            thumbnail = self._pad_thumbnail(thumbnail, target_side)
            qimage = ImageQt.ImageQt(thumbnail)
            pixmap = QtGui.QPixmap.fromImage(qimage)

            image_label = ClickableLabel(partial(start_file, item_id), alignment=QtCore.Qt.AlignCenter)
            image_label.setPixmap(pixmap)
            image_label.setStyleSheet("background-color: #1C1D21;")
            image_label.setMinimumSize(1, 1)

            controls_container = QtWidgets.QWidget()
            controls = QtWidgets.QHBoxLayout(controls_container)
            controls.setContentsMargins(0, 0, 0, 0)
            controls.setSpacing(4)
            move_button = QtWidgets.QPushButton("M")
            move_button.clicked.connect(partial(self.move_item, item_id))
            id_button = QtWidgets.QPushButton(str(item_id))
            id_button.clicked.connect(partial(start_file, item_id))
            delete_button = QtWidgets.QPushButton("X")
            delete_button.clicked.connect(partial(self.delete_item, item_id))

            controls.addWidget(move_button)
            controls.addWidget(id_button)
            controls.addWidget(delete_button)

            if not pixmap.isNull():
                controls_container.setFixedWidth(pixmap.width())
            card_layout.setAlignment(QtCore.Qt.AlignTop | QtCore.Qt.AlignHCenter)
            card_layout.addWidget(image_label, 0, QtCore.Qt.AlignHCenter)
            card_layout.addWidget(controls_container, 0, QtCore.Qt.AlignHCenter)

            self.scroll_layout.addWidget(card, row, col)
            ids_per_row[-1].append(item_id)
            col += 1
            if col >= columns:
                row += 1
                col = 0

        for idx, row_ids in enumerate(ids_per_row):
            button = QtWidgets.QPushButton("Open row")
            button.clicked.connect(partial(self.open_items, row_ids))
            self.scroll_layout.addWidget(button, idx, columns)

        self.scroll_area.verticalScrollBar().setValue(self.scrollbar_y_pos)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.ids:
            self._resize_timer.start(150)

    def refresh_reset(self):
        self.id_data = {}
        self.load_next_items()

    def move_item(self, item_id):
        path = Item.objects.get(id=item_id).getpath()
        pil_image = Image.open(path)
        pil_image = crop_and_resize_image(
            pil_image, (0, pil_image.width, 0, pil_image.height)
        )
        pil_image.save(path)

        edit_item(
            item_id=item_id,
            new_state=int(FileState.NeedsLabel),
            new_width=pil_image.width,
            new_height=pil_image.height,
        )
        self.load_next_items()

    def open_items(self, item_ids):
        for item_id in item_ids:
            os.startfile(Item.objects.filter(id=item_id).get().getpath())

    def delete_item(self, item_id):
        delete_items({item_id})
        self.load_next_items()

    def closeEvent(self, event):
        if not self.completed:
            self.window_closed_manually = True
        super().closeEvent(event)


def start_modify_application():
    if not get_top_x_needsmodify_ids(1):
        return True, True
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)
    window = ModifyApplication()
    if window.completed:
        return not window.window_closed_manually, window.completed
    window.showMaximized()
    window.raise_()
    window.activateWindow()
    app.exec()
    return not window.window_closed_manually, window.completed


if __name__ == "__main__":
    start_modify_application()
