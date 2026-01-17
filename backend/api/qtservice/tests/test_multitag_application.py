import pytest
from PIL import Image

from api.qtservice import multitag_application as multitag_app


@pytest.fixture
def multitag_window(monkeypatch, qtbot):
    monkeypatch.setattr(multitag_app, "check_for_crops", lambda: False)
    monkeypatch.setattr(multitag_app, "check_for_modify", lambda: False)
    monkeypatch.setattr(multitag_app, "check_for_unlabelled", lambda: False)
    monkeypatch.setattr(multitag_app, "get_all_labels", lambda *a, **k: [])
    monkeypatch.setattr(multitag_app, "get_untagged_ids", lambda *a, **k: [1])
    monkeypatch.setattr(multitag_app, "get_thumbnail", lambda *a, **k: Image.new("RGB", (10, 10)))
    monkeypatch.setattr(multitag_app, "add_tags", lambda *a, **k: None)

    class _FakeItem:
        def getpath(self):
            return ""

    class _FakeItemManager:
        def filter(self, id):
            return self

        def get(self):
            return _FakeItem()

    class _FakeItemModel:
        objects = _FakeItemManager()

    monkeypatch.setattr(multitag_app, "Item", _FakeItemModel)

    window = multitag_app.MultiTagApplication(tag_names=["test"])
    qtbot.addWidget(window)
    return window


def test_add_tags_clears_selection(monkeypatch, multitag_window):
    called = []
    monkeypatch.setattr(multitag_app, "add_tags", lambda *a, **k: called.append(True))
    multitag_window.selected_ids = {1}
    multitag_window.tag_value_entry.setText("value")
    multitag_window.add_tags_to_selected()

    assert called
    assert multitag_window.selected_ids == set()


def test_no_items_completes(monkeypatch, qtbot):
    monkeypatch.setattr(multitag_app, "check_for_crops", lambda: False)
    monkeypatch.setattr(multitag_app, "check_for_modify", lambda: False)
    monkeypatch.setattr(multitag_app, "check_for_unlabelled", lambda: False)
    monkeypatch.setattr(multitag_app, "get_untagged_ids", lambda *a, **k: [])
    monkeypatch.setattr(multitag_app, "get_all_labels", lambda *a, **k: [])
    window = multitag_app.MultiTagApplication(tag_names=["test"])
    qtbot.addWidget(window)
    assert window.completed
