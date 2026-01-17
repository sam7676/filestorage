from PIL import Image
import pytest

from api.models import FileType, FileState
from api.qtservice import view_application as view_app
from PySide6 import QtWidgets


class _FakeItem:
    def __init__(self, item_id, filetype=FileType.Image, width=80, height=40, label="cat"):
        self.id = item_id
        self.filetype = int(filetype)
        self.width = width
        self.height = height
        self.label = label

    def getpath(self):
        return ""


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
def view_window(monkeypatch, qtbot):
    items = [_FakeItem(1), _FakeItem(2), _FakeItem(3)]
    manager = _FakeManager(items)

    monkeypatch.setattr(view_app, "get_items_and_paths_from_tags", lambda *a, **k: {1: {}, 2: {}, 3: {}})
    monkeypatch.setattr(view_app, "get_tags", lambda *a, **k: {"label": ["cat"]})
    monkeypatch.setattr(view_app, "get_tag", lambda *a, **k: 1)
    monkeypatch.setattr(view_app, "get_thumbnail", lambda *a, **k: Image.new("RGB", (10, 10)))
    monkeypatch.setattr(view_app, "delete_items", lambda *a, **k: None)
    monkeypatch.setattr(view_app, "edit_item", lambda *a, **k: None)

    class _FakeItemModel:
        objects = manager

    monkeypatch.setattr(view_app, "Item", _FakeItemModel)

    window = view_app.ViewApplication()
    qtbot.addWidget(window)
    return window


def test_builds_bins(view_window):
    assert view_window.item_ids
    assert view_window.bins


def test_toggle_thumbnail_mode(view_window):
    current = view_window.thumbnail_mode
    view_window.toggle_thumbnail_mode()
    assert view_window.thumbnail_mode != current


def test_modify_mode_gates_actions(view_window):
    view_window.modify_mode = False
    view_window.load_items()
    buttons = view_window.items_scroll_contents.findChildren(QtWidgets.QPushButton)
    assert any(not b.isEnabled() for b in buttons)
