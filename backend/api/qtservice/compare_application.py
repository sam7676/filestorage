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
import vlc


VIDEOS_CURRENTLY_PLAYED = 2
COMPARE_MEDIA_HEIGHT_SCALE = 1.5


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


class CompareApplication(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.window_closed_manually = False
        self.completed = False

        self.item = None
        self.comparison_item_ids = []
        self.video_widgets = {}

        self.setWindowTitle("Compare")
        screen = QtGui.QGuiApplication.primaryScreen()
        if screen:
            geometry = screen.availableGeometry()
            width = int(geometry.width() * 0.85)
            height = int(geometry.height() * 0.85)
            self.resize(width, height)
            self._set_crop_limits(geometry.width(), geometry.height())
        else:
            self.resize(1500, 900)
            self._set_crop_limits(1500, 900)

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
        layout.setSpacing(0)

        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.scroll_contents = QtWidgets.QWidget()
        self.scroll_layout = QtWidgets.QHBoxLayout(self.scroll_contents)
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_layout.setSpacing(0)
        self.scroll_layout.setAlignment(QtCore.Qt.AlignHCenter | QtCore.Qt.AlignVCenter)
        self.scroll_area.setWidget(self.scroll_contents)
        self.scroll_contents.setStyleSheet("background-color: #1C1D21;")

        self.next_button = QtWidgets.QPushButton("Next")
        self.next_button.setMinimumHeight(48)
        self.next_button.clicked.connect(self.next)

        layout.addWidget(self.scroll_area, 1)
        next_row = QtWidgets.QHBoxLayout()
        next_row.addWidget(self.next_button)
        layout.addLayout(next_row, 0)

        QtGui.QShortcut(QtGui.QKeySequence("Return"), self, activated=self.next)

    def _set_crop_limits(self, available_width, available_height):
        base_height = max(1, int(available_height * 0.4))
        scaled_height = int(base_height * COMPARE_MEDIA_HEIGHT_SCALE)
        self.max_height_in_crop = min(max(1, scaled_height), max(1, available_height))
        self.max_width_of_crop = max(1, int(available_width * 0.4))
        self.min_height_in_crop = min(self.max_height_in_crop, 160)

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

    def _clear_video_players(self):
        for widget in list(self.video_widgets.values()):
            widget.close()
        self.video_widgets = {}

    def _resize_thumbnail(self, thumbnail, target_height):
        resample = getattr(Image, "Resampling", Image).LANCZOS
        if thumbnail.height != target_height:
            scale = target_height / thumbnail.height
            new_size = (
                max(1, int(thumbnail.width * scale)),
                max(1, int(thumbnail.height * scale)),
            )
            thumbnail = thumbnail.resize(new_size, resample=resample)
        return thumbnail

    def _build_card(self, item_id, target_height, allow_video, is_main=False):
        item = Item.objects.filter(id=item_id).get()
        new_height = max(1, int(target_height))
        new_width = max(1, int(item.width * new_height / item.height))

        card = QtWidgets.QFrame()
        card.setFrameShape(QtWidgets.QFrame.NoFrame)
        card_layout = QtWidgets.QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        image_container = QtWidgets.QWidget()
        image_container_layout = QtWidgets.QVBoxLayout(image_container)
        image_container_layout.setContentsMargins(0, 0, 0, 0)
        if item.filetype == int(FileType.Video) and allow_video:
            video_widget = VlcVideoWidget()
            video_widget.setFixedSize(new_width, new_height)
            video_widget.set_media(item.getpath())
            video_widget.play()
            video_widget.mousePressEvent = (
                lambda event, item_id=item_id: self.open_item(item_id)
            )
            image_container_layout.addWidget(
                video_widget, 0, QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter
            )
            self.video_widgets[item_id] = video_widget
            media_width = new_width
        else:
            resized_image = get_thumbnail(item.id, new_width, new_height)
            resized_image = self._resize_thumbnail(resized_image, new_height)
            qimage = ImageQt.ImageQt(resized_image)
            pixmap = QtGui.QPixmap.fromImage(qimage)
            pixmap = pixmap.scaled(
                new_width,
                new_height,
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation,
            )
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
            image_container_layout.addWidget(
                image_button, 0, QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter
            )
            media_width = pixmap.width()
        image_container.setFixedHeight(new_height)
        image_container.setSizePolicy(
            QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Fixed
        )

        footer = QtWidgets.QWidget()
        footer_layout = QtWidgets.QHBoxLayout(footer)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.setSpacing(6)
        footer_layout.setAlignment(QtCore.Qt.AlignCenter)

        id_label = QtWidgets.QLabel(str(item_id))
        id_label.setAlignment(QtCore.Qt.AlignCenter)
        id_label.setStyleSheet(
            "color: #FF6666; background-color: #1C1D21; font-weight: bold; font-size: 16px;"
        )
        id_label.setSizePolicy(
            QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Fixed
        )

        remove_button = QtWidgets.QPushButton("⨯")
        remove_button.clicked.connect(partial(self.remove_item, item_id))
        remove_button.setFlat(True)
        remove_button.setStyleSheet(
            "border: none; padding: 2px 6px; margin: 0; color: #FF6666; background-color: #1C1D21; font-weight: bold; font-size: 16px;"
        )
        remove_button.setSizePolicy(
            QtWidgets.QSizePolicy.Maximum, QtWidgets.QSizePolicy.Fixed
        )
        remove_button.setMinimumWidth(0)

        footer_layout.addWidget(id_label)
        footer_layout.addWidget(remove_button)
        footer.setMaximumWidth(media_width)

        card_layout.addWidget(
            image_container, 1, QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter
        )
        card_layout.addWidget(
            footer, 0, QtCore.Qt.AlignHCenter | QtCore.Qt.AlignBottom
        )

        return card

    def load_items(self):
        self._clear_video_players()
        self._clear_layout(self.scroll_layout)

        viewport_width = self.scroll_area.viewport().width()
        spacing = self.scroll_layout.spacing()
        if viewport_width <= 0:
            QtCore.QTimer.singleShot(0, self.load_items)
            return

        target_height = self.max_height_in_crop
        cards = []
        total_width = 0
        items = []
        if self.item:
            items.append((self.item.id, self.item, True))
        for item_id in self.comparison_item_ids:
            items.append((item_id, Item.objects.filter(id=item_id).get(), False))

        for item_id, item, is_main in items:
            width_at_h = max(1, int(item.width * target_height / item.height))
            gap = spacing if cards else 0
            if total_width + gap + width_at_h <= viewport_width:
                cards.append((item_id, target_height, is_main))
                total_width += gap + width_at_h
                continue

            remaining = viewport_width - total_width - gap - 2
            if remaining <= 0:
                break
            target_height_last = max(1, int(target_height * 0.8))
            width_at_last = max(1, int(item.width * target_height_last / item.height))
            if (
                target_height_last >= self.min_height_in_crop
                and width_at_last <= remaining
            ):
                cards.append((item_id, target_height_last, is_main))
            break

        videos_started = 0
        for item_id, height, is_main in cards:
            item_type = Item.objects.filter(id=item_id).get().filetype
            allow_video = (
                item_type == int(FileType.Video)
                and videos_started < VIDEOS_CURRENTLY_PLAYED
            )
            self.scroll_layout.addWidget(
                self._build_card(item_id, height, allow_video, is_main=is_main)
            )
            if allow_video:
                videos_started += 1

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
        self._clear_video_players()
        if not self.completed:
            self.window_closed_manually = True
        super().closeEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        viewport = self.scroll_area.viewport()
        if viewport:
            self._set_crop_limits(viewport.width(), viewport.height())
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
