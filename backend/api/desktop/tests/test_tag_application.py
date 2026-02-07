from pathlib import Path

from PIL import Image
import pytest
from PySide6 import QtWidgets

from api.models import FileType
from api.desktop import tag_application as tag_app


class _FakeItem:
    def __init__(self, path, filetype, width=100, height=100, label="test"):
        self._path = path
        self.filetype = int(filetype)
        self.width = width
        self.height = height
        self.label = label

    def getpath(self):
        return self._path


class _FakeManager:
    def __init__(self, item):
        self._item = item

    def filter(self, id):
        return self

    def get(self):
        return self._item


def _make_image(tmp_path: Path) -> str:
    image_path = tmp_path / "sample.png"
    Image.new("RGB", (64, 64), (10, 10, 10)).save(image_path)
    return str(image_path)


@pytest.fixture
def tag_app_window(tmp_path, monkeypatch, qtbot):
    image_path = _make_image(tmp_path)
    fake_item = _FakeItem(image_path, FileType.Image, width=64, height=64)

    monkeypatch.setattr(tag_app, "get_next_tag_item", lambda *a, **k: 1)
    monkeypatch.setattr(tag_app, "get_tags", lambda item_id: {"label": ["test"]})
    monkeypatch.setattr(tag_app, "get_latest_confirmed_item", lambda *a, **k: None)
    monkeypatch.setattr(tag_app, "get_distinct_tags", lambda: [("color", "red")])
    monkeypatch.setattr(tag_app, "add_tags", lambda *a, **k: None)
    monkeypatch.setattr(tag_app, "remove_tags", lambda *a, **k: None)
    monkeypatch.setattr(tag_app, "delete_items_desktop", lambda *a, **k: None)
    monkeypatch.setattr(tag_app, "edit_item", lambda *a, **k: None)

    class _FakeItemModel:
        objects = _FakeManager(fake_item)

    monkeypatch.setattr(tag_app, "Item", _FakeItemModel)

    window = tag_app.TagApplication(tag_random=False)
    qtbot.addWidget(window)
    return window


def test_resize_triggers_tag_reload(tag_app_window, qtbot):
    triggered = []

    def on_timeout():
        triggered.append(True)

    tag_app_window._resize_timer.timeout.disconnect()
    tag_app_window._resize_timer.timeout.connect(on_timeout)

    tag_app_window.show()
    qtbot.wait(50)
    tag_app_window.resize(tag_app_window.width() + 50, tag_app_window.height() + 50)
    qtbot.waitUntil(lambda: bool(triggered), timeout=1000)

    assert triggered


def test_color_buttons_use_tooltips(tag_app_window):
    buttons = tag_app_window.suggested_scroll_contents.findChildren(
        QtWidgets.QPushButton
    )
    color_buttons = [b for b in buttons if b.toolTip() in tag_app.COLOR_DATA_NAMES]
    assert color_buttons
    assert all(b.text() == "" for b in color_buttons)


def test_video_label_edit_closes_media(tmp_path, monkeypatch, qtbot):
    image_path = _make_image(tmp_path)
    fake_item = _FakeItem(image_path, FileType.Video, width=64, height=64)

    class _FakeItemModel:
        objects = _FakeManager(fake_item)

    monkeypatch.setattr(tag_app, "Item", _FakeItemModel)
    monkeypatch.setattr(tag_app, "edit_item", lambda *a, **k: None)
    monkeypatch.setattr(tag_app, "get_next_tag_item", lambda *a, **k: 1)
    monkeypatch.setattr(tag_app, "get_tags", lambda item_id: {"label": ["test"]})
    monkeypatch.setattr(tag_app, "get_latest_confirmed_item", lambda *a, **k: None)
    monkeypatch.setattr(tag_app, "get_distinct_tags", lambda: [])
    monkeypatch.setattr(tag_app, "add_tags", lambda *a, **k: None)
    monkeypatch.setattr(tag_app, "remove_tags", lambda *a, **k: None)
    monkeypatch.setattr(tag_app, "delete_items_desktop", lambda *a, **k: None)

    window = tag_app.TagApplication(tag_random=False)
    qtbot.addWidget(window)

    closed = []
    window._close_media_player = lambda: closed.append(True)
    window.item = fake_item

    entry = QtWidgets.QLineEdit()
    entry.setText("newlabel")
    window.new_label(entry)

    assert closed
