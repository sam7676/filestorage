from api.views_extension import (
    get_next_clip_item,
    get_nearest_item,
    get_thumbnail,
    edit_item,
    delete_items,
    start_file,
    ClipModel,
)
from api.models import Item, FileType, FileState
from functools import partial
import sys

from PIL import ImageQt
from PySide6 import QtCore, QtGui, QtWidgets
import vlc


VIDEOS_TO_PLAY = 0


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


class ClipApplication(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.window_closed_manually = False
        self.completed = False

        self.item_id = None
        self.nearest_item_id = None
        self.swap = False
        self._last_item_id = None
        self._last_nearest_item_id = None
        self._video_widgets = []
        self._screen_geometry = None
        self.videos_to_play = VIDEOS_TO_PLAY

        self.setWindowTitle("Clip application")
        screen = QtGui.QGuiApplication.primaryScreen()
        if screen:
            geometry = screen.availableGeometry()
            self._screen_geometry = geometry
            width = int(geometry.width() * 0.85)
            height = int(geometry.height() * 0.85)
            self.resize(width, height)
            self.max_height_in_crop = int(geometry.height() * 0.92)
            self.max_width_of_crop = int(geometry.width() * 0.7)
        else:
            self.resize(1500, 900)
            self.max_height_in_crop = 1040
            self.max_width_of_crop = 1200

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
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.items_layout = QtWidgets.QHBoxLayout()
        self.items_layout.setSpacing(8)

        self.left_item_frame = QtWidgets.QFrame()
        self.right_item_frame = QtWidgets.QFrame()
        self.left_item_frame.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.right_item_frame.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.left_layout = QtWidgets.QVBoxLayout(self.left_item_frame)
        self.right_layout = QtWidgets.QVBoxLayout(self.right_item_frame)
        self.left_layout.setContentsMargins(0, 0, 0, 0)
        self.right_layout.setContentsMargins(0, 0, 0, 0)

        self.items_layout.addWidget(self.left_item_frame, 1)
        self.items_layout.addWidget(self.right_item_frame, 1)

        buttons_layout = QtWidgets.QVBoxLayout()
        buttons_layout.setSpacing(6)

        top_buttons = QtWidgets.QHBoxLayout()
        top_buttons.setSpacing(6)
        bottom_buttons = QtWidgets.QHBoxLayout()
        bottom_buttons.setSpacing(6)

        self.keep_left_button = QtWidgets.QPushButton("Left")
        self.keep_both_button = QtWidgets.QPushButton("Both")
        self.keep_right_button = QtWidgets.QPushButton("Right")
        self.keep_none_button = QtWidgets.QPushButton("None")
        self.swap_button = QtWidgets.QPushButton("Swap")

        top_buttons.addStretch(1)
        top_buttons.addWidget(self.keep_left_button)
        top_buttons.addWidget(self.keep_both_button)
        top_buttons.addWidget(self.keep_right_button)
        top_buttons.addStretch(1)

        bottom_buttons.addStretch(1)
        bottom_buttons.addWidget(self.keep_none_button)
        bottom_buttons.addWidget(self.swap_button)
        bottom_buttons.addStretch(1)

        buttons_layout.addLayout(top_buttons)
        buttons_layout.addLayout(bottom_buttons)

        layout.addLayout(self.items_layout, 1)
        layout.addLayout(buttons_layout, 0)

        self.keep_left_button.clicked.connect(self.choose_left)
        self.keep_both_button.clicked.connect(self.choose_middle)
        self.keep_right_button.clicked.connect(self.choose_right)
        self.keep_none_button.clicked.connect(self.choose_none)
        self.swap_button.clicked.connect(self.change_swap)

        QtGui.QShortcut(
            QtGui.QKeySequence("Return"), self, activated=self.choose_middle
        )

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

    def _update_media_constraints(self):
        rect = self.items_layout.geometry()
        if rect.height() <= 0 or rect.width() <= 0:
            if self._screen_geometry:
                available_height = self._screen_geometry.height()
                available_width = self._screen_geometry.width()
            else:
                available_height = self.height()
                available_width = self.width()
        else:
            available_height = rect.height()
            available_width = rect.width()

        available_height = max(1, available_height - 48)
        spacing = self.items_layout.spacing()
        self.max_height_in_crop = max(1, int(available_height))
        self.max_width_of_crop = max(1, int((available_width - spacing) / 2))

    def load_next_item(self):
        item_id = get_next_clip_item()
        if item_id is None:
            self.completed = True
            self.close()
            return

        item = Item.objects.get(id=item_id)
        nearest_item_id = get_nearest_item(item_id, item.label, item.filetype)

        self.item_id = item_id
        self.nearest_item_id = nearest_item_id

        if self.nearest_item_id == -1:
            self.approve(self.item_id)
            return

        self.swap = False

        self._last_item_id = self.item_id
        self._last_nearest_item_id = self.nearest_item_id

        self.load_items()

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _clear_video_players(self):
        for widget in self._video_widgets:
            widget.close()
        self._video_widgets = []

    def _get_widget(self, item_id, frame_layout, align):
        item = Item.objects.filter(id=item_id).get()
        self._update_media_constraints()

        new_width = int(round(item.width * self.max_height_in_crop / item.height))
        new_height = self.max_height_in_crop
        if new_width > self.max_width_of_crop:
            new_width = self.max_width_of_crop
            new_height = int(round(new_width * item.height / item.width))

        use_video_player = (
            item.filetype == int(FileType.Video) and self.videos_to_play > 0
        )
        if use_video_player:
            widget = VlcVideoWidget()
            widget.setFixedSize(new_width, new_height)
            widget.set_media(item.getpath())
            widget.play()
            self._video_widgets.append(widget)
            self.videos_to_play -= 1
        else:
            resized_image = get_thumbnail(item.id, new_width, new_height)

        if not use_video_player:
            qimage = ImageQt.ImageQt(resized_image)
            pixmap = QtGui.QPixmap.fromImage(qimage)
            pixmap = pixmap.scaled(
                new_width,
                new_height,
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation,
            )

            if item.filetype == int(FileType.Image):
                widget = QtWidgets.QPushButton()
                widget.setIcon(QtGui.QIcon(pixmap))
                widget.setIconSize(pixmap.size())
                widget.clicked.connect(partial(start_file, item.id))
                widget.setFlat(True)
                widget.setStyleSheet("border: none;")
            else:
                widget = QtWidgets.QLabel()
                widget.setPixmap(pixmap)
                widget.setStyleSheet("background-color: #1C1D21; border: none;")

        widget.setStyleSheet("background-color: #1C1D21; border: none;")
        frame_layout.addWidget(widget, 1, align)

        type_to_str_map = {0: "image", 1: "video"}
        type_label = QtWidgets.QLabel(type_to_str_map[item.filetype])
        type_label.setStyleSheet("color: #E6E6E6;")
        type_label.setSizePolicy(
            QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Fixed
        )

        id_label = QtWidgets.QLabel(str(item_id))
        id_label.setAlignment(QtCore.Qt.AlignCenter)
        id_label.setSizePolicy(
            QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Fixed
        )

        label_row = QtWidgets.QHBoxLayout()
        label_row.addWidget(id_label)
        label_row.addWidget(type_label)
        frame_layout.addLayout(label_row, 0)

    def load_items(self):
        self._clear_video_players()
        self._clear_layout(self.left_layout)
        self._clear_layout(self.right_layout)
        self.videos_to_play = VIDEOS_TO_PLAY

        self.left_item_id = self.item_id if not self.swap else self.nearest_item_id
        self.right_item_id = self.nearest_item_id if not self.swap else self.item_id

        self._get_widget(self.left_item_id, self.left_layout, QtCore.Qt.AlignRight)
        self._get_widget(self.right_item_id, self.right_layout, QtCore.Qt.AlignLeft)

        self.swap_button.setStyleSheet(
            "color: #FF0000;" if self.swap else "color: #E6E6E6;"
        )

    def approve(self, item_id):
        edit_item(item_id=item_id, new_state=int(FileState.NeedsTags))
        self.load_next_item()

    def delete(self, item_id):
        delete_items((item_id,))
        self.load_next_item()

    def choose_left(self):
        self.delete(self.right_item_id)

    def choose_middle(self):
        self.approve(self.item_id)

    def choose_right(self):
        self.delete(self.left_item_id)

    def choose_none(self):
        self.delete(self.left_item_id)
        self.delete(self.right_item_id)

    def change_swap(self):
        self.swap = not self.swap
        self.load_items()

    def closeEvent(self, event):
        self._clear_video_players()
        if not self.completed:
            self.window_closed_manually = True
        super().closeEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.item_id is not None:
            self._resize_timer.start(100)


def start_clip_application():
    
    ClipModel.process_unclipped_items()
    
    if get_next_clip_item() is None:
        return True, True
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)
    window = ClipApplication()
    if window.completed:
        return not window.window_closed_manually, window.completed
    window.showMaximized()
    window.raise_()
    window.activateWindow()
    app.exec()
    return not window.window_closed_manually, window.completed


if __name__ == "__main__":
    start_clip_application()
