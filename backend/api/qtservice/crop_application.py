from api.views_extension import (
    get_next_crop_item,
    crop_and_resize_from_view,
    delete_items,
)
from api.utils.process_images import apply_rgb_curves
from api.utils.process_images import rotate_image_90
from api.models import FileState
from math import ceil
import sys

from PIL import ImageQt
from PySide6 import QtCore, QtGui, QtWidgets


SCALE_CONSTANT = 2


class CropGraphicsView(QtWidgets.QGraphicsView):
    def __init__(self, on_left_click, on_right_click, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._on_left_click = on_left_click
        self._on_right_click = on_right_click

    def mousePressEvent(self, event):
        pos = self.mapToScene(event.pos())
        if event.button() == QtCore.Qt.LeftButton:
            self._on_left_click(pos)
        elif event.button() == QtCore.Qt.RightButton:
            self._on_right_click(pos)
        super().mousePressEvent(event)


class CropApplication(QtWidgets.QMainWindow):
    def __init__(self):
        # Image max height is 0.7 * screen height if screen exists, else 700

        super().__init__()
        self.window_closed_manually = False
        self._closing_for_complete = False
        self.completed = False

        self.item_id = None
        self.image = None
        self.bounds = []
        self.bounds_ind = 0
        self.scale = SCALE_CONSTANT
        self.scale_ind = 1
        self.alpha = 0.0
        self.rotation_degrees = 0

        self.left_canvas_cords = None
        self.right_canvas_cords = None
        self.selection_items = []

        self.setWindowTitle("Crop application")
        screen = QtGui.QGuiApplication.primaryScreen()
        if screen:
            geometry = screen.availableGeometry()
            width = int(geometry.width() * 0.85)
            height = int(geometry.height() * 0.85)
            self.resize(width, height)
            self.max_height_in_crop = int(geometry.height() * 0.7)
        else:
            self.resize(1500, 900)
            self.max_height_in_crop = 700

        self._build_ui()
        self._apply_dark_theme()
        self.load_next_item()

    def _build_ui(self):
        # Margins: are they necessary?
        # Spacing is 8
        # Look at slider - goes between -100 and 100 in this version, do we want this?

        root = QtWidgets.QWidget(self)
        self.setCentralWidget(root)

        main_layout = QtWidgets.QVBoxLayout(root)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        content_layout = QtWidgets.QHBoxLayout()
        content_layout.setSpacing(8)

        self.scene = QtWidgets.QGraphicsScene()
        self.view = CropGraphicsView(self._left_click, self._right_click)
        self.view.setScene(self.scene)
        self.view.setRenderHints(
            QtGui.QPainter.Antialiasing | QtGui.QPainter.SmoothPixmapTransform
        )
        self.view.setBackgroundBrush(QtGui.QColor("#1C1D21"))
        self.view.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.view.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
        )
        self.view.setMinimumSize(1, 1)

        self.preview_label = QtWidgets.QLabel()
        self.preview_label.setAlignment(QtCore.Qt.AlignCenter)
        self.preview_label.setStyleSheet("background-color: #1C1D21;")
        self.preview_label.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
        )
        self.preview_label.setMinimumSize(1, 1)

        self.slider = QtWidgets.QSlider(QtCore.Qt.Vertical)
        self.slider.setRange(-100, 100)
        self.slider.setValue(0)
        self.slider.setSingleStep(1)
        self.slider.setPageStep(10)
        self.slider.sliderReleased.connect(self.on_slider_release)

        # Stretch factors are used to change how much space widgets are given in proportion to one another
        # 3, 3, 0 here says image gets 50% and preview gets 50% of width

        content_layout.addWidget(self.view, 3)
        content_layout.addWidget(self.preview_label, 3)
        content_layout.addWidget(self.slider, 0)

        buttons_layout = QtWidgets.QHBoxLayout()
        buttons_layout.setSpacing(6)

        self.delete_button = QtWidgets.QPushButton("Delete")
        self.confirm_button = QtWidgets.QPushButton("Enter")
        self.scale_label = QtWidgets.QPushButton(f"Scale: {self.scale_ind}")
        self.bounds_label = QtWidgets.QPushButton(f"Bounds: {self.bounds_ind} / 0")
        self.bounds_label.clicked.connect(self.reset_bounds)
        self.modify_button = QtWidgets.QPushButton("Modify")
        self.modify_copy_button = QtWidgets.QPushButton("Modify Copy")
        self.copy_button = QtWidgets.QPushButton("Copy")
        self.rotate_button = QtWidgets.QPushButton("Rotate 90")

        for btn in (
            self.delete_button,
            self.confirm_button,
            self.scale_label,
            self.bounds_label,
            self.modify_button,
            self.modify_copy_button,
            self.copy_button,
            self.rotate_button,
        ):
            buttons_layout.addWidget(btn)

        main_layout.addLayout(content_layout, 1)
        main_layout.addLayout(buttons_layout, 0)

        self.delete_button.clicked.connect(self.delete)
        self.confirm_button.clicked.connect(self.confirm)
        self.modify_button.clicked.connect(self.modify)
        self.modify_copy_button.clicked.connect(self.modify_copy)
        self.copy_button.clicked.connect(self.copy)
        self.rotate_button.clicked.connect(self.rotate_90)

        QtGui.QShortcut(QtGui.QKeySequence("Return"), self, activated=self.confirm)
        QtGui.QShortcut(QtGui.QKeySequence("Delete"), self, activated=self.delete)
        QtGui.QShortcut(QtGui.QKeySequence("c"), self, activated=self.copy)
        QtGui.QShortcut(QtGui.QKeySequence("m"), self, activated=self.modify)
        QtGui.QShortcut(QtGui.QKeySequence("n"), self, activated=self.modify_copy)
        QtGui.QShortcut(QtGui.QKeySequence("r"), self, activated=self.reset_bounds)

        QtGui.QShortcut(
            QtGui.QKeySequence("w"), self, activated=lambda: self.move_up(1)
        )
        QtGui.QShortcut(
            QtGui.QKeySequence("a"), self, activated=lambda: self.move_left(1)
        )
        QtGui.QShortcut(
            QtGui.QKeySequence("s"), self, activated=lambda: self.move_down(1)
        )
        QtGui.QShortcut(
            QtGui.QKeySequence("d"), self, activated=lambda: self.move_right(1)
        )

        QtGui.QShortcut(
            QtGui.QKeySequence("Up"), self, activated=lambda: self.move_up(2)
        )
        QtGui.QShortcut(
            QtGui.QKeySequence("Left"), self, activated=lambda: self.move_left(2)
        )
        QtGui.QShortcut(
            QtGui.QKeySequence("Down"), self, activated=lambda: self.move_down(2)
        )
        QtGui.QShortcut(
            QtGui.QKeySequence("Right"), self, activated=lambda: self.move_right(2)
        )

        QtGui.QShortcut(QtGui.QKeySequence("["), self, activated=self.decrease_scale)
        QtGui.QShortcut(QtGui.QKeySequence("]"), self, activated=self.increase_scale)
        QtGui.QShortcut(
            QtGui.QKeySequence("PgUp"), self, activated=self.decrease_bounds
        )
        QtGui.QShortcut(
            QtGui.QKeySequence("PgDown"), self, activated=self.increase_bounds
        )
        QtGui.QShortcut(QtGui.QKeySequence("t"), self, activated=self.rotate_90)

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
            QSlider::groove:vertical { background: #2B2E35; width: 6px; }
            QSlider::handle:vertical { background: #6E7179; height: 18px; }
            """
        )

    def load_next_item(self):
        data = get_next_crop_item(self.max_height_in_crop)

        # Out of items, close window
        if data is None:
            self._closing_for_complete = True
            self.completed = True
            self.hide()
            QtCore.QTimer.singleShot(0, self.close)
            app = QtWidgets.QApplication.instance()
            if app:
                QtCore.QTimer.singleShot(0, app.quit)
            return

        image, bounds, item_id = data
        self.image = image
        self.bounds = bounds
        self.item_id = item_id
        self.alpha = 0.0
        self.rotation_degrees = 0
        self.slider.setValue(0)

        self.scale = SCALE_CONSTANT
        self.scale_ind = 1
        self.scale_label.setText(f"Scale: {self.scale_ind}")

        self._load_image()

    def _load_image(self):
        self._set_pixmap_from_image()

        self.left_canvas_cords = None
        self.right_canvas_cords = None

        self.bounds_ind = 0
        self.bounds_label.setText(
            f"Bounds: {min(self.bounds_ind + 1, len(self.bounds))} / {len(self.bounds)}"
        )

        if self.bounds:
            x1, x2, y1, y2 = self.bounds[self.bounds_ind]
            self.left_canvas_cords = [x1, y1]
            self.right_canvas_cords = [x2, y2]
        else:
            self.left_canvas_cords = (0, 0)
            self.right_canvas_cords = (self.image.width, self.image.height)

        self._fit_view()
        self.make_rectangle_canvas()

    def _set_pixmap_from_image(self):
        self.scene.clear()
        self.selection_items = []
        qimage = ImageQt.ImageQt(self.image)
        pixmap = QtGui.QPixmap.fromImage(qimage)
        self.pixmap_item = self.scene.addPixmap(pixmap)
        self.pixmap_item.setTransformationMode(QtCore.Qt.SmoothTransformation)
        self.scene.setSceneRect(0, 0, self.image.width, self.image.height)

    def _fit_view(self):
        self.view.fitInView(self.scene.sceneRect(), QtCore.Qt.KeepAspectRatio)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.image:
            self._fit_view()
            self._update_preview()

    def _left_click(self, pos):
        self.left_canvas_cords = (int(pos.x()), int(pos.y()))
        self.make_rectangle_canvas()

    def _right_click(self, pos):
        self.right_canvas_cords = (int(pos.x()), int(pos.y()))
        self.make_rectangle_canvas()

    def reset_bounds(self):
        if not self.image:
            return
        self.left_canvas_cords = (0, 0)
        self.right_canvas_cords = (self.image.width, self.image.height)
        self.make_rectangle_canvas()

    def make_rectangle_canvas(self):
        for item in self.selection_items:
            self.scene.removeItem(item)
        self.selection_items = []

        if self.left_canvas_cords and self.right_canvas_cords:
            left_x, left_y = self.left_canvas_cords
            right_x, right_y = self.right_canvas_cords

            if left_x == right_x:
                left_x = max(left_x - 1, 0)
                right_x = min(right_x + 1, self.image.width)

            if left_y == right_y:
                left_y = max(left_y - 1, 0)
                right_y = min(right_y + 1, self.image.height)

            x1 = min(left_x, right_x)
            y1 = min(left_y, right_y)
            x2 = max(left_x, right_x)
            y2 = max(left_y, right_y)

            self.left_canvas_cords = (x1, y1)
            self.right_canvas_cords = (x2, y2)

            pen = QtGui.QPen(QtGui.QColor("red"))
            pen.setWidth(1)
            rect = self.scene.addRect(x1, y1, x2 - x1, y2 - y1, pen)
            self.selection_items.append(rect)

        if self.left_canvas_cords:
            x, y = self.left_canvas_cords
            marker = self.scene.addRect(
                x - 3,
                y - 3,
                6,
                6,
                QtGui.QPen(QtGui.QColor("green")),
                QtGui.QBrush(QtGui.QColor("green")),
            )
            self.selection_items.append(marker)

        if self.right_canvas_cords:
            x, y = self.right_canvas_cords
            marker = self.scene.addRect(
                x - 3,
                y - 3,
                6,
                6,
                QtGui.QPen(QtGui.QColor("blue")),
                QtGui.QBrush(QtGui.QColor("blue")),
            )
            self.selection_items.append(marker)

        self._update_preview()

    def rotate_90(self):
        if not self.image:
            return
        self.rotation_degrees = (self.rotation_degrees + 90) % 360
        self._update_preview()

    def _update_preview(self):
        if not (self.left_canvas_cords and self.right_canvas_cords):
            self.preview_label.clear()
            return

        preview = self.image.crop(
            (
                self.left_canvas_cords[0],
                self.left_canvas_cords[1],
                self.right_canvas_cords[0],
                self.right_canvas_cords[1],
            )
        )
        preview = apply_rgb_curves(preview, self.alpha)
        if self.rotation_degrees:
            preview = rotate_image_90(preview, turns=self.rotation_degrees // 90)
        qimage = ImageQt.ImageQt(preview)
        pixmap = QtGui.QPixmap.fromImage(qimage)
        self.preview_label.setPixmap(
            pixmap.scaled(
                self.preview_label.size(),
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation,
            )
        )

    def confirm(self):
        self._apply_crop(FileState.NeedsLabel, "save")

    def copy(self):
        self._apply_crop(FileState.NeedsLabel, "new")

    def modify(self):
        self._apply_crop(FileState.NeedsModify, "save")

    def modify_copy(self):
        self._apply_crop(FileState.NeedsModify, "new")

    def _apply_crop(self, new_state, save_or_new):
        crop = (None, None, None, None)
        if self.left_canvas_cords and self.right_canvas_cords:
            x1, y1 = self.left_canvas_cords
            x2, y2 = self.right_canvas_cords
            if None not in (x1, x2, y1, y2):
                crop = (x1, x2, y1, y2)

        crop_and_resize_from_view(
            item_id=self.item_id,
            rendered_size=(self.image.width, self.image.height),
            crop=crop,
            new_state=new_state,
            save_or_new=save_or_new,
            alpha=self.alpha,
            rotate_degrees=self.rotation_degrees,
        )
        self.load_next_item()

    def delete(self):
        delete_items(item_ids=(self.item_id,))
        self.load_next_item()

    def move_up(self, val):
        if val == 1 and self.left_canvas_cords:
            y = max(self.left_canvas_cords[1] - self.scale, 0)
            self.left_canvas_cords = (self.left_canvas_cords[0], y)
            self.make_rectangle_canvas()
        elif val == 2 and self.right_canvas_cords:
            y = max(self.right_canvas_cords[1] - self.scale, 0)
            self.right_canvas_cords = (self.right_canvas_cords[0], y)
            self.make_rectangle_canvas()

    def move_down(self, val):
        if val == 1 and self.left_canvas_cords:
            y = min(self.left_canvas_cords[1] + self.scale, self.image.height)
            self.left_canvas_cords = (self.left_canvas_cords[0], y)
            self.make_rectangle_canvas()
        elif val == 2 and self.right_canvas_cords:
            y = min(self.right_canvas_cords[1] + self.scale, self.image.height)
            self.right_canvas_cords = (self.right_canvas_cords[0], y)
            self.make_rectangle_canvas()

    def move_left(self, val):
        if val == 1 and self.left_canvas_cords:
            x = max(self.left_canvas_cords[0] - self.scale, 0)
            self.left_canvas_cords = (x, self.left_canvas_cords[1])
            self.make_rectangle_canvas()
        elif val == 2 and self.right_canvas_cords:
            x = max(self.right_canvas_cords[0] - self.scale, 0)
            self.right_canvas_cords = (x, self.right_canvas_cords[1])
            self.make_rectangle_canvas()

    def move_right(self, val):
        if val == 1 and self.left_canvas_cords:
            x = min(self.left_canvas_cords[0] + self.scale, self.image.width)
            self.left_canvas_cords = (x, self.left_canvas_cords[1])
            self.make_rectangle_canvas()
        elif val == 2 and self.right_canvas_cords:
            x = min(self.right_canvas_cords[0] + self.scale, self.image.width)
            self.right_canvas_cords = (x, self.right_canvas_cords[1])
            self.make_rectangle_canvas()

    def decrease_scale(self):
        self.scale = ceil(self.scale / SCALE_CONSTANT)
        self.scale_ind = max(0, self.scale_ind - 1)
        self.scale_label.setText(f"Scale: {self.scale_ind}")

    def increase_scale(self):
        self.scale = ceil(self.scale * SCALE_CONSTANT)
        self.scale_ind += 1
        self.scale_label.setText(f"Scale: {self.scale_ind}")

    def increase_bounds(self):
        if self.bounds:
            self.bounds_ind = (self.bounds_ind + 1) % len(self.bounds)
            x1, x2, y1, y2 = self.bounds[self.bounds_ind]
            self.left_canvas_cords = (x1, y1)
            self.right_canvas_cords = (x2, y2)
            self.make_rectangle_canvas()

        self.bounds_label.setText(
            f"Bounds: {min(self.bounds_ind + 1, len(self.bounds))} / {len(self.bounds)}"
        )

    def decrease_bounds(self):
        if self.bounds:
            self.bounds_ind = (self.bounds_ind - 1) % len(self.bounds)
            x1, x2, y1, y2 = self.bounds[self.bounds_ind]
            self.left_canvas_cords = (x1, y1)
            self.right_canvas_cords = (x2, y2)
            self.make_rectangle_canvas()

        self.bounds_label.setText(
            f"Bounds: {min(self.bounds_ind + 1, len(self.bounds))} / {len(self.bounds)}"
        )

    def on_slider_release(self):
        self.alpha = float(self.slider.value() / 100.0)
        self._update_preview()

    def closeEvent(self, event):
        if not self._closing_for_complete:
            self.window_closed_manually = True
        super().closeEvent(event)


def start_crop_application():
    # Setting height as 0.7 * screen again

    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)
    screen = QtGui.QGuiApplication.primaryScreen()
    if screen:
        geometry = screen.availableGeometry()
        max_height_in_crop = int(geometry.height() * 0.7)
    else:
        max_height_in_crop = 700
    if get_next_crop_item(max_height_in_crop) is None:
        return True, True
    window = CropApplication()
    window.showMaximized()
    window.raise_()
    window.activateWindow()
    app.exec()
    return not window.window_closed_manually, window.completed


if __name__ == "__main__":
    start_crop_application()
