from PIL import Image
import pytest

from api.models import FileType
from api.qtservice import compare_application as compare_app


class _FakeItem:
    def __init__(self, item_id, filetype=FileType.Image, width=80, height=40):
        self.id = item_id
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
def compare_window(monkeypatch, qtbot):
    items = [_FakeItem(1), _FakeItem(2), _FakeItem(3)]
    manager = _FakeManager(items)

    monkeypatch.setattr(compare_app, "get_random_compare_item", lambda *a, **k: items[0])
    monkeypatch.setattr(compare_app, "get_comparison_items", lambda *a, **k: [2, 3])
    monkeypatch.setattr(compare_app, "get_thumbnail", lambda *a, **k: Image.new("RGB", (10, 10)))
    monkeypatch.setattr(compare_app, "delete_items", lambda *a, **k: None)

    class _FakeItemModel:
        objects = manager

    monkeypatch.setattr(compare_app, "Item", _FakeItemModel)

    window = compare_app.CompareApplication()
    qtbot.addWidget(window)
    return window


def test_remove_item_updates_list(monkeypatch, compare_window):
    called = []
    monkeypatch.setattr(compare_app, "delete_items", lambda ids: called.append(ids))

    compare_window.remove_item(2)

    assert called == [{2}]
    assert 2 not in compare_window.comparison_item_ids


def test_next_loads_new_item(monkeypatch, compare_window):
    items = [_FakeItem(10), _FakeItem(11)]
    manager = _FakeManager(items)
    monkeypatch.setattr(compare_app, "get_random_compare_item", lambda *a, **k: items[1])
    monkeypatch.setattr(compare_app, "get_comparison_items", lambda *a, **k: [])
    monkeypatch.setattr(compare_app.Item, "objects", manager)

    compare_window.next()

    assert compare_window.item.id == 11
