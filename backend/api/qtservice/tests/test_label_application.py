from pathlib import Path

from PIL import Image
import pytest

from api.models import FileState
from api.qtservice import label_application as label_app
from PySide6 import QtWidgets


def _make_image(tmp_path: Path) -> str:
    image_path = tmp_path / "sample.png"
    Image.new("RGB", (80, 40), (20, 20, 20)).save(image_path)
    return str(image_path)


@pytest.fixture
def label_window(tmp_path, monkeypatch, qtbot):
    image_path = _make_image(tmp_path)
    monkeypatch.setattr(label_app, "get_top_x_unlabelled_ids", lambda *a, **k: [1])
    monkeypatch.setattr(label_app, "get_all_labels", lambda *a, **k: [{"label": "cat"}])
    monkeypatch.setattr(label_app, "get_thumbnail", lambda *a, **k: Image.new("RGB", (10, 10)))
    monkeypatch.setattr(label_app, "edit_item", lambda *a, **k: None)

    window = label_app.LabelApplication()
    qtbot.addWidget(window)
    return window


def test_label_suggestions_render(label_window):
    label_window.entry_bar.setText("c")
    label_window.on_entry_change()

    labels = label_window.results_container.findChildren(QtWidgets.QLabel)
    assert any(label.text() == "cat" for label in labels)


def test_modify_items_calls_edit(monkeypatch, label_window):
    captured = {}

    def _capture(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(label_app, "edit_item", _capture)
    label_window.selected_ids = {1}
    label_window.modify_items("dog")

    assert captured["new_label"] == "dog"
    assert captured["new_state"] == int(FileState.NeedsClip)


def test_no_items_closes(monkeypatch, qtbot):
    monkeypatch.setattr(label_app, "get_top_x_unlabelled_ids", lambda *a, **k: [])
    monkeypatch.setattr(label_app, "get_all_labels", lambda *a, **k: [])
    window = label_app.LabelApplication()
    qtbot.addWidget(window)
    assert window.completed
