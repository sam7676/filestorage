from pathlib import Path

from PIL import Image
import pytest

from api.models import FileState
from api.qtservice import crop_application as crop_app


def _make_image(tmp_path: Path) -> Image.Image:
    image_path = tmp_path / "sample.png"
    Image.new("RGB", (80, 60), (20, 20, 20)).save(image_path)
    return Image.open(image_path)


@pytest.fixture
def crop_window(tmp_path, monkeypatch, qtbot):
    image = _make_image(tmp_path)
    bounds = [(10, 40, 5, 30)]
    items = iter([(image, bounds, 123), None])

    monkeypatch.setattr(crop_app, "get_next_crop_item", lambda *a, **k: next(items))
    monkeypatch.setattr(crop_app, "delete_items", lambda *a, **k: None)

    window = crop_app.CropApplication()
    qtbot.addWidget(window)
    return window


def test_reset_bounds_sets_full_image(crop_window):
    crop_window.reset_bounds()
    assert crop_window.left_canvas_cords == (0, 0)
    assert crop_window.right_canvas_cords == (
        crop_window.image.width,
        crop_window.image.height,
    )


def test_confirm_applies_crop(monkeypatch, crop_window):
    captured = {}

    def _capture(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(crop_app, "crop_and_resize_from_view", _capture)
    crop_window.left_canvas_cords = (5, 6)
    crop_window.right_canvas_cords = (20, 30)
    crop_window.rotation_degrees = 90

    crop_window.confirm()

    assert captured["item_id"] == 123
    assert captured["crop"] == (5, 20, 6, 30)
    assert captured["new_state"] == FileState.NeedsLabel
    assert captured["save_or_new"] == "save"
    assert captured["rotate_degrees"] == 90


def test_slider_updates_alpha(crop_window):
    crop_window.slider.setValue(50)
    crop_window.on_slider_release()
    assert crop_window.alpha == pytest.approx(0.5)


def test_rotate_updates_dimensions(crop_window):
    original_width = crop_window.image.width
    original_height = crop_window.image.height

    crop_window.rotate_90()

    assert crop_window.rotation_degrees == 90
    assert crop_window.image.width == original_width
    assert crop_window.image.height == original_height


def test_no_bounds_defaults_to_full_image(tmp_path, monkeypatch, qtbot):
    image = _make_image(tmp_path)
    items = iter([(image, [], 234), None])

    monkeypatch.setattr(crop_app, "get_next_crop_item", lambda *a, **k: next(items))
    monkeypatch.setattr(crop_app, "delete_items", lambda *a, **k: None)

    window = crop_app.CropApplication()
    qtbot.addWidget(window)

    assert window.left_canvas_cords == (0, 0)
    assert window.right_canvas_cords == (window.image.width, window.image.height)
