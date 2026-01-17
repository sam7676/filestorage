from pathlib import Path

from PIL import Image
import pytest

from api.models import FileState
from api.qtservice import modify_application as modify_app


class _FakeItem:
    def __init__(self, path):
        self._path = path

    def getpath(self):
        return self._path


class _FakeManager:
    def __init__(self, item):
        self._item = item

    def get(self, id):
        return self._item

    def filter(self, id):
        return self


def _make_image(tmp_path: Path) -> str:
    image_path = tmp_path / "sample.png"
    Image.new("RGB", (80, 40), (20, 20, 20)).save(image_path)
    return str(image_path)


@pytest.fixture
def modify_window(tmp_path, monkeypatch, qtbot):
    image_path = _make_image(tmp_path)
    fake_item = _FakeItem(image_path)
    fake_manager = _FakeManager(fake_item)

    monkeypatch.setattr(modify_app, "get_top_x_needsmodify_ids", lambda *a, **k: [1])
    monkeypatch.setattr(modify_app, "get_thumbnail", lambda *a, **k: Image.new("RGB", (10, 10)))
    monkeypatch.setattr(modify_app, "delete_items", lambda *a, **k: None)
    monkeypatch.setattr(modify_app, "edit_item", lambda *a, **k: None)
    monkeypatch.setattr(modify_app, "start_file", lambda *a, **k: None)

    class _FakeItemModel:
        objects = fake_manager

    monkeypatch.setattr(modify_app, "Item", _FakeItemModel)

    window = modify_app.ModifyApplication()
    qtbot.addWidget(window)
    return window


def test_move_item_updates_item(monkeypatch, modify_window):
    captured = {}

    def _capture(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(modify_app, "edit_item", _capture)

    modify_window.move_item(1)

    assert captured["item_id"] == 1
    assert captured["new_state"] == int(FileState.NeedsLabel)
    assert captured["new_width"] > 0
    assert captured["new_height"] > 0


def test_delete_item_calls_delete(monkeypatch, modify_window):
    called = []
    monkeypatch.setattr(modify_app, "delete_items", lambda ids: called.append(ids))

    modify_window.delete_item(1)

    assert called == [{1}]


def test_no_items_closes(tmp_path, monkeypatch, qtbot):
    monkeypatch.setattr(modify_app, "get_top_x_needsmodify_ids", lambda *a, **k: [])
    window = modify_app.ModifyApplication()
    qtbot.addWidget(window)
    assert window.completed
