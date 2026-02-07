from PIL import Image
import pytest

from api.models import FileType, FileState
from api.desktop import clip_application as clip_app
from PySide6 import QtWidgets


class _FakeItem:
    def __init__(
        self, item_id, label="cat", filetype=FileType.Image, width=80, height=40
    ):
        self.id = item_id
        self.label = label
        self.filetype = int(filetype)
        self.width = width
        self.height = height


class _FakeManager:
    def __init__(self, items):
        self._items = {item.id: item for item in items}
        self._filtered_id = None

    def get(self, id=None, **kwargs):
        item_id = id if id is not None else kwargs.get("id")
        if item_id is None:
            item_id = self._filtered_id
        return self._items[item_id]

    def filter(self, id=None, **kwargs):
        self._filtered_id = id if id is not None else kwargs.get("id")
        return self


@pytest.fixture
def clip_window(monkeypatch, qtbot):
    items = [_FakeItem(1), _FakeItem(2)]
    manager = _FakeManager(items)

    monkeypatch.setattr(clip_app, "get_next_clip_item", lambda *a, **k: 1)
    monkeypatch.setattr(clip_app, "get_nearest_item", lambda *a, **k: 2)
    monkeypatch.setattr(
        clip_app, "get_thumbnail", lambda *a, **k: Image.new("RGB", (10, 10))
    )
    monkeypatch.setattr(clip_app, "edit_item", lambda *a, **k: None)
    monkeypatch.setattr(clip_app, "delete_items_desktop", lambda *a, **k: None)
    monkeypatch.setattr(clip_app, "start_file", lambda *a, **k: None)

    class _FakeItemModel:
        objects = manager

    monkeypatch.setattr(clip_app, "Item", _FakeItemModel)

    window = clip_app.ClipApplication()
    qtbot.addWidget(window)
    return window


def test_choose_left_deletes_right(monkeypatch, clip_window):
    called = []
    monkeypatch.setattr(
        clip_app, "delete_items_desktop", lambda ids: called.append(ids)
    )

    clip_window.choose_left()

    assert called == [(clip_window.right_item_id,)]


def test_nearest_missing_auto_approves(monkeypatch, qtbot):
    items_iter = iter([1, None])
    monkeypatch.setattr(
        clip_app, "get_next_clip_item", lambda *a, **k: next(items_iter)
    )
    monkeypatch.setattr(clip_app, "get_nearest_item", lambda *a, **k: -1)
    monkeypatch.setattr(
        clip_app, "get_thumbnail", lambda *a, **k: Image.new("RGB", (10, 10))
    )
    approved = []
    monkeypatch.setattr(clip_app, "edit_item", lambda **kwargs: approved.append(kwargs))

    class _FakeItemModel:
        objects = _FakeManager([_FakeItem(1)])

    monkeypatch.setattr(clip_app, "Item", _FakeItemModel)

    window = clip_app.ClipApplication()
    qtbot.addWidget(window)

    assert approved
    assert approved[0]["new_state"] == int(FileState.NeedsTags)


def test_clear_layout_removes_nested_widgets(qtbot, clip_window):
    container = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(container)
    child_layout = QtWidgets.QHBoxLayout()

    label = QtWidgets.QLabel("meta")
    child_layout.addWidget(label)
    layout.addLayout(child_layout)
    layout.addWidget(QtWidgets.QLabel("media"))

    clip_window._clear_layout(layout)
    QtWidgets.QApplication.processEvents()

    assert layout.count() == 0
    assert child_layout.count() == 0


def test_toggle_videos_updates_state_and_button(clip_window):
    assert clip_window.show_videos is False
    assert clip_window.videos_to_play == 0
    assert clip_window.toggle_videos_button.text() == "Show Videos"

    clip_window.toggle_videos()

    assert clip_window.show_videos is True
    assert clip_window.videos_to_play == 2
    assert clip_window.toggle_videos_button.text() == "Hide Videos"
