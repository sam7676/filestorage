import importlib
import io
import math
import sys
import tempfile
import types
from pathlib import Path
from unittest.mock import patch

import numpy as np
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from api import models as api_models
from api import views_extension
from api.views_extension import add_tags, crop_and_resize_from_view


class ItemModelTests(TestCase):
    def setUp(self):
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.old_media_path = api_models.MEDIA_PATH
        api_models.MEDIA_PATH = self.temp_dir.name
        self.addCleanup(setattr, api_models, "MEDIA_PATH", self.old_media_path)

    # When we create an item, check it goes to uncropped
    def test_item_path_and_parent(self):
        item = api_models.Item.objects.create(
            state=int(api_models.FileState.NeedsCrop),
            label="",
            filetype=int(api_models.FileType.Image),
            width=640,
            height=480,
        )

        expected_path = f"{api_models.MEDIA_PATH}/uncropped/{item.getstringid()}.png"
        self.assertEqual(item.getpath(), expected_path)
        self.assertEqual(item.getparent(), str(Path(expected_path).parent))

    # Checking get file properties works as expected
    def test_get_file_properties_parses_label_and_type(self):
        path = f"{api_models.MEDIA_PATH}/items/cat/0000000123.jpg"
        properties = api_models.get_file_properties(path)

        self.assertEqual(properties["name"], "0000000123")
        self.assertEqual(properties["label"], "cat")
        self.assertEqual(properties["category"], "items")
        self.assertEqual(properties["type"], int(api_models.FileType.Image))

    # Checking item ID matches as expected
    def test_try_get_item_returns_item_when_id_matches(self):
        item = api_models.Item.objects.create(
            state=int(api_models.FileState.NeedsLabel),
            label="",
            filetype=int(api_models.FileType.Image),
            width=100,
            height=100,
        )

        found_item, properties = api_models.try_get_item(item.getpath())
        self.assertEqual(found_item.id, item.id)
        self.assertEqual(properties["name"], item.getstringid())


@override_settings(SECURE_SSL_REDIRECT=False)
class ApiViewTests(TestCase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        user = User.objects.create_user(username="tester", password="pass")
        token = AccessToken.for_user(user)
        self.client.cookies["access_token"] = str(token)

    def _build_white_image_file(self, name="white.png", size=(10, 10)):
        buffer = io.BytesIO()
        image = Image.new("RGB", size, color="white")
        image.save(buffer, format="PNG")
        buffer.seek(0)
        return SimpleUploadedFile(name, buffer.read(), content_type="image/png")

    def test_check_auth_with_cookie_token(self):
        response = self.client.post("/api/checkauth")
        self.assertEqual(response.status_code, 200)

    def test_file_upload_calls_image_handler(self):
        image_file = self._build_white_image_file()
        with patch("api.views.upload_image") as upload_image:
            response = self.client.post(
                "/api/upload",
                {"image": image_file},
                format="multipart",
            )

        self.assertEqual(response.status_code, 200)
        upload_image.assert_called_once()

    def test_file_upload_calls_video_handler(self):
        video_file = SimpleUploadedFile(
            "sample.mp4",
            b"fake video bytes",
            content_type="video/mp4",
        )
        with patch("api.views.upload_video") as upload_video:
            response = self.client.post(
                "/api/upload",
                {"video": video_file},
                format="multipart",
            )

        self.assertEqual(response.status_code, 200)
        upload_video.assert_called_once()
        called_args = upload_video.call_args[0]
        self.assertEqual(called_args[0].name, "sample.mp4")

    def test_delete_item_calls_delete(self):
        with patch("api.views.delete_items") as delete_items:
            response = self.client.post(
                "/api/delete",
                {"item_id": 123},
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        delete_items.assert_called_once_with({123})


@override_settings(SECURE_SSL_REDIRECT=False)
class RandomItemApiTests(TestCase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        user = User.objects.create_user(username="tester", password="pass")
        token = AccessToken.for_user(user)
        self.client.cookies["access_token"] = str(token)
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

    def _build_items(self, labels):
        items = {}
        for idx, label in enumerate(labels, start=1):
            path = Path(self.temp_dir.name) / f"{idx}.png"
            path.write_bytes(b"data")
            items[idx] = {
                "path": str(path),
                "mime_type": "image/png",
                "label": label,
                "width": 1,
                "height": 1,
                "filetype": int(api_models.FileType.Image),
            }
        return items

    def _post_random(self, method, items):
        captured = {}

        def fake_get_items(tags):
            captured["tags"] = tags
            return items

        def fake_choices(keys, weights=None, k=None):
            captured["keys"] = keys
            captured["weights"] = weights
            return [keys[0]]

        with (
            patch(
                "api.views.get_items_and_paths_from_tags", side_effect=fake_get_items
            ),
            patch("api.views.random.choices", side_effect=fake_choices),
        ):
            response = self.client.post(
                "/api/download",
                {
                    "type": "image",
                    "tags": [{"name": "random", "condition": "is", "value": method}],
                },
                format="json",
            )

        response.close()
        return response, captured

    def test_random_item_recent_weights(self):
        items = self._build_items(["cat", "dog", "bird"])
        response, captured = self._post_random("recent", items)

        self.assertEqual(response.status_code, 200)
        expected = [
            1 / (3 * len(captured["keys"]) / 2 - i)
            for i in range(len(captured["keys"]))
        ]
        for actual, target in zip(captured["weights"], expected):
            self.assertTrue(math.isclose(actual, target, rel_tol=1e-6))
        self.assertTrue(all(key[0] != "random" for key in captured["tags"]))

    def test_random_item_sparse_weights(self):
        items = self._build_items(["cat", "cat", "dog"])
        response, captured = self._post_random("sparse", items)

        self.assertEqual(response.status_code, 200)
        expected = [1 / math.sqrt(2), 1 / math.sqrt(2), 1.0]
        for actual, target in zip(captured["weights"], expected):
            self.assertTrue(math.isclose(actual, target, rel_tol=1e-6))

    def test_random_item_dense_weights(self):
        items = self._build_items(["cat", "cat", "dog"])
        response, captured = self._post_random("dense", items)

        self.assertEqual(response.status_code, 200)
        expected = [math.sqrt(2), math.sqrt(2), 1.0]
        for actual, target in zip(captured["weights"], expected):
            self.assertTrue(math.isclose(actual, target, rel_tol=1e-6))


class ProcessImagesTests(TestCase):
    def _import_process_images(self):
        dummy_ultralytics = types.ModuleType("ultralytics")

        class DummyYOLO:
            def __init__(self, *args, **kwargs):
                pass

            def __call__(self, *args, **kwargs):
                return [[]]

        dummy_ultralytics.YOLO = DummyYOLO

        with patch.dict(sys.modules, {"ultralytics": dummy_ultralytics}):
            if "api.utils.process_images" in sys.modules:
                del sys.modules["api.utils.process_images"]
            return importlib.import_module("api.utils.process_images")

    def test_crop_and_resize_white_canvas(self):
        process_images = self._import_process_images()
        image = Image.new("RGB", (200, 100), color="white")
        resized = process_images.crop_and_resize_image(image, corners=(0, 100, 0, 50))

        self.assertEqual(resized.size[1], process_images.MEDIA_HEIGHT)

    def test_apply_rgb_curves_identity_and_adjusted(self):
        process_images = self._import_process_images()
        image = Image.new("RGB", (10, 10), color="white")

        same_image = process_images.apply_rgb_curves(image, 0.0)
        self.assertIs(same_image, image)

        adjusted_image = process_images.apply_rgb_curves(image, 0.5)
        self.assertIsNot(adjusted_image, image)
        self.assertEqual(adjusted_image.size, image.size)

    def test_build_curve_from_slider_output(self):
        process_images = self._import_process_images()
        curve = process_images.build_curve_from_slider(0.25)
        self.assertEqual(len(curve), 256)
        self.assertTrue(all(0 <= value <= 255 for value in curve))

    def test_build_curve_from_slider_identity_at_zero(self):
        process_images = self._import_process_images()
        curve = process_images.build_curve_from_slider(0.0)
        self.assertEqual(curve[0], 0)
        self.assertEqual(curve[128], 128)
        self.assertEqual(curve[255], 255)

    def test_build_curve_from_slider_is_monotonic(self):
        process_images = self._import_process_images()
        curve = process_images.build_curve_from_slider(0.8)
        self.assertTrue(all(curve[i] <= curve[i + 1] for i in range(len(curve) - 1)))

    def test_build_curve_from_slider_clamps_input(self):
        process_images = self._import_process_images()
        curve_hi = process_images.build_curve_from_slider(2.5)
        curve_lo = process_images.build_curve_from_slider(-2.5)
        self.assertEqual(len(curve_hi), 256)
        self.assertEqual(len(curve_lo), 256)
        self.assertEqual(min(curve_hi), 0)
        self.assertEqual(max(curve_hi), 255)
        self.assertEqual(min(curve_lo), 0)
        self.assertEqual(max(curve_lo), 255)

    def test_get_crop_image_and_bounds_calls_get_bounds(self):
        process_images = self._import_process_images()
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.png"
            Image.new("RGB", (200, 100), color="white").save(path)

            with patch.object(process_images, "get_bounds") as get_bounds:
                get_bounds.return_value = [(1, 2, 3, 4)]
                image, bounds = process_images.get_crop_image_and_bounds(
                    str(path), crop_max_height=50, include_bounds=True
                )

            self.assertEqual(image.size, (50, 25))
            self.assertEqual(bounds, [(1, 2, 3, 4)])
            get_bounds.assert_called_once()

    def test_get_crop_image_and_bounds_without_bounds(self):
        process_images = self._import_process_images()
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.png"
            Image.new("RGB", (100, 200), color="white").save(path)

            image = process_images.get_crop_image_and_bounds(
                str(path), crop_max_height=50, include_bounds=False
            )

        self.assertEqual(image.size, (25, 50))

    def test_clean_corners_orders_and_clamps(self):
        process_images = self._import_process_images()
        image = Image.new("RGB", (10, 10), color="white")
        x1, x2, y1, y2 = process_images.clean_corners(image, corners=(-10, 20, 15, -5))

        self.assertGreaterEqual(x1, 0)
        self.assertGreaterEqual(y1, 0)
        self.assertLessEqual(x2, image.width)
        self.assertLessEqual(y2, image.height)
        self.assertLess(x1, x2)
        self.assertLess(y1, y2)

    def test_crop_and_resize_clips_and_orders(self):
        process_images = self._import_process_images()
        image = Image.new("RGB", (100, 50), color="white")
        resized = process_images.crop_and_resize_image(
            image, corners=(80, -10, 60, -20)
        )

        self.assertEqual(resized.size[1], process_images.MEDIA_HEIGHT)

    def test_apply_rgb_curves_adjusts_midtones(self):
        process_images = self._import_process_images()
        image = Image.new("RGB", (2, 2), color=(128, 128, 128))

        adjusted_image = process_images.apply_rgb_curves(image, 0.5)

        self.assertIsNot(adjusted_image, image)
        self.assertNotEqual(adjusted_image.getpixel((0, 0)), image.getpixel((0, 0)))

    def test_apply_rgb_curves_converts_grayscale(self):
        process_images = self._import_process_images()
        image = Image.new("L", (3, 3), color=128)

        adjusted_image = process_images.apply_rgb_curves(image, 0.4)

        self.assertEqual(adjusted_image.mode, "RGB")
        self.assertEqual(adjusted_image.size, image.size)

    def test_rotate_image_90_changes_dimensions(self):
        process_images = self._import_process_images()
        image = Image.new("RGB", (80, 40), color="white")

        rotated = process_images.rotate_image_90(image, turns=1)

        self.assertEqual(rotated.size, (40, 80))

    def test_get_bounds_orders_person_before_other(self):
        process_images = self._import_process_images()
        image = Image.new("RGB", (10, 10), color="white")

        class DummyBoxes:
            def __init__(self):
                self.xyxy = process_images.np.array(
                    [
                        [1, 2, 3, 4],
                        [4, 5, 6, 7],
                    ],
                    dtype=float,
                )
                self.cls = process_images.np.array([1, 0])
                self._len = len(self.xyxy)

            def __len__(self):
                return self._len

        class DummyBound:
            def __init__(self):
                self.boxes = DummyBoxes()

        def fake_model(_image, verbose=False):
            return [[DummyBound()]]

        def reorder_to_xyxy(_img, corners):
            x1, x2, y1, y2 = corners
            return x1, y1, x2, y2

        with (
            patch.object(process_images, "bounding_box_model", fake_model),
            patch.object(process_images, "clean_corners", side_effect=reorder_to_xyxy),
        ):
            bounds = process_images.get_bounds(image)

        self.assertEqual(bounds[0], (4.0, 5.0, 6.0, 7.0))
        self.assertEqual(bounds[1], (1.0, 2.0, 3.0, 4.0))

    def test_get_bounds_empty_response(self):
        process_images = self._import_process_images()
        image = Image.new("RGB", (10, 10), color="white")

        def fake_model(_image, verbose=False):
            return [[]]

        with patch.object(process_images, "bounding_box_model", fake_model):
            bounds = process_images.get_bounds(image)

        self.assertEqual(bounds, [])

    def test_get_bounds_calls_clean_corners_per_box(self):
        process_images = self._import_process_images()
        image = Image.new("RGB", (10, 10), color="white")

        class DummyBoxes:
            def __init__(self):
                self.xyxy = process_images.np.array(
                    [
                        [1, 2, 3, 4],
                        [4, 5, 6, 7],
                    ],
                    dtype=float,
                )
                self.cls = process_images.np.array([0, 1])
                self._len = len(self.xyxy)

            def __len__(self):
                return self._len

        class DummyBound:
            def __init__(self):
                self.boxes = DummyBoxes()

        def fake_model(_image, verbose=False):
            return [[DummyBound()]]

        with (
            patch.object(process_images, "bounding_box_model", fake_model),
            patch.object(
                process_images,
                "clean_corners",
                side_effect=lambda _img, corners: corners,
            ) as clean_corners,
        ):
            process_images.get_bounds(image)

        self.assertEqual(clean_corners.call_count, 2)

    def test_clean_corners_grayscale_input(self):
        process_images = self._import_process_images()
        image = Image.new("L", (20, 10), color=128)
        x1, x2, y1, y2 = process_images.clean_corners(image, corners=(-5, 25, 12, -3))

        self.assertGreaterEqual(x1, 0)
        self.assertGreaterEqual(y1, 0)
        self.assertLessEqual(x2, image.width)
        self.assertLessEqual(y2, image.height)
        self.assertLess(x1, x2)
        self.assertLess(y1, y2)

    def test_crop_and_resize_handles_float_coords(self):
        process_images = self._import_process_images()
        image = Image.new("RGB", (120, 80), color="white")
        resized = process_images.crop_and_resize_image(
            image, corners=(60.5, 10.2, -5.5, 70.9)
        )

        self.assertEqual(resized.size[1], process_images.MEDIA_HEIGHT)


class ViewsExtensionTests(TestCase):
    def setUp(self):
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.old_media_path = api_models.MEDIA_PATH
        api_models.MEDIA_PATH = self.temp_dir.name
        self.addCleanup(setattr, api_models, "MEDIA_PATH", self.old_media_path)

    def test_crop_and_resize_from_view_rotates(self):
        item = api_models.Item.objects.create(
            state=int(api_models.FileState.NeedsCrop),
            label="",
            filetype=int(api_models.FileType.Image),
            width=80,
            height=40,
        )

        path = Path(item.getpath())
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (80, 40), color="white").save(path)

        views_extension.crop_and_resize_from_view(
            item_id=item.id,
            rendered_size=(40, 80),
            crop=(0, 40, 0, 80),
            new_state=api_models.FileState.NeedsLabel,
            save_or_new="save",
            alpha=0.0,
            rotate_degrees=90,
        )

        item.refresh_from_db()
        rotated_path = Path(item.getpath())
        rotated = Image.open(rotated_path)
        self.assertEqual(
            rotated.size,
            (views_extension.MEDIA_HEIGHT, views_extension.MEDIA_HEIGHT * 2),
        )

    def test_crop_and_resize_from_view_no_rotation(self):
        item = api_models.Item.objects.create(
            state=int(api_models.FileState.NeedsCrop),
            label="",
            filetype=int(api_models.FileType.Image),
            width=80,
            height=40,
        )

        path = Path(item.getpath())
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (80, 40), color="white").save(path)

        views_extension.crop_and_resize_from_view(
            item_id=item.id,
            rendered_size=(80, 40),
            crop=(0, 80, 0, 40),
            new_state=api_models.FileState.NeedsLabel,
            save_or_new="save",
            alpha=0.0,
            rotate_degrees=0,
        )

        item.refresh_from_db()
        resized_path = Path(item.getpath())
        resized = Image.open(resized_path)
        self.assertEqual(resized.size, (1600, views_extension.MEDIA_HEIGHT))


class DesktopPipelineTests(TestCase):
    def setUp(self):
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.old_media_path = api_models.MEDIA_PATH
        api_models.MEDIA_PATH = self.temp_dir.name
        self.addCleanup(setattr, api_models, "MEDIA_PATH", self.old_media_path)

    def _create_image_item(self, state, size=(80, 40)):
        item = api_models.Item.objects.create(
            state=int(state),
            label="",
            filetype=int(api_models.FileType.Image),
            width=size[0],
            height=size[1],
        )
        path = Path(item.getpath())
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", size, color="white").save(path)
        return item

    def _create_video_item(self, state):
        item = api_models.Item.objects.create(
            state=int(state),
            label="",
            filetype=int(api_models.FileType.Video),
            width=320,
            height=180,
        )
        path = Path(item.getpath())
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake video bytes")
        return item

    def test_pipeline_image_to_complete_with_label_edit(self):
        item = self._create_image_item(api_models.FileState.NeedsCrop)

        crop_and_resize_from_view(
            item_id=item.id,
            rendered_size=(80, 40),
            crop=(0, 80, 0, 40),
            new_state=api_models.FileState.NeedsModify,
            save_or_new="save",
            alpha=0.0,
        )

        item.refresh_from_db()
        self.assertEqual(item.state, int(api_models.FileState.NeedsModify))

        image = Image.open(item.getpath())
        resized = views_extension.crop_and_resize_image(
            image, (0, image.width, 0, image.height)
        )
        resized.save(item.getpath())
        views_extension.edit_item(
            item_id=item.id,
            new_state=int(api_models.FileState.NeedsLabel),
            new_width=resized.width,
            new_height=resized.height,
        )

        item.refresh_from_db()
        self.assertEqual(item.state, int(api_models.FileState.NeedsLabel))

        views_extension.edit_item(
            item_id=item.id,
            new_label="cat",
            new_state=int(api_models.FileState.NeedsClip),
        )

        add_tags({item.id: {"color": ["red"], "source": ["internal"]}})

        with patch.object(
            views_extension.ClipModel, "process_item", return_value=np.zeros(8)
        ):
            views_extension.ClipModel.process_unclipped_items()

        views_extension.edit_item(
            item_id=item.id, new_state=int(api_models.FileState.NeedsTags)
        )
        views_extension.edit_item(item_id=item.id, new_label="dog")
        views_extension.edit_item(
            item_id=item.id, new_state=int(api_models.FileState.Complete)
        )

        item.refresh_from_db()
        self.assertEqual(item.state, int(api_models.FileState.Complete))
        self.assertEqual(item.label, "dog")

        labelplus_values = set(
            api_models.Tags.objects.filter(
                item_id=item.id, name="labelplus"
            ).values_list("value", flat=True)
        )
        self.assertIn("dog", labelplus_values)

    def test_pipeline_video_skips_crop_modify(self):
        item = self._create_video_item(api_models.FileState.NeedsLabel)

        views_extension.edit_item(
            item_id=item.id,
            new_label="clip",
            new_state=int(api_models.FileState.NeedsClip),
        )
        add_tags({item.id: {"source": ["internal"]}})

        with patch.object(
            views_extension.ClipModel, "process_item", return_value=np.zeros(8)
        ):
            views_extension.ClipModel.process_unclipped_items()

        views_extension.edit_item(
            item_id=item.id, new_state=int(api_models.FileState.NeedsTags)
        )
        views_extension.edit_item(
            item_id=item.id, new_state=int(api_models.FileState.Complete)
        )

        item.refresh_from_db()
        self.assertEqual(item.state, int(api_models.FileState.Complete))

    def test_crop_creates_second_item(self):
        item = self._create_image_item(api_models.FileState.NeedsCrop)

        crop_and_resize_from_view(
            item_id=item.id,
            rendered_size=(80, 40),
            crop=(10, 70, 5, 35),
            new_state=api_models.FileState.NeedsLabel,
            save_or_new="new",
            alpha=0.0,
        )

        self.assertEqual(api_models.Item.objects.count(), 2)

    def test_crop_inverted_coords_still_resizes(self):
        item = self._create_image_item(api_models.FileState.NeedsCrop)

        crop_and_resize_from_view(
            item_id=item.id,
            rendered_size=(80, 40),
            crop=(70, 10, 35, 5),
            new_state=api_models.FileState.NeedsModify,
            save_or_new="save",
            alpha=0.0,
        )

        item.refresh_from_db()
        image = Image.open(item.getpath())
        self.assertEqual(image.size[1], views_extension.MEDIA_HEIGHT)


class CleanDbTests(TestCase):
    def setUp(self):
        super().setUp()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.old_media_path = api_models.MEDIA_PATH
        api_models.MEDIA_PATH = self.temp_dir.name
        self.addCleanup(setattr, api_models, "MEDIA_PATH", self.old_media_path)

        self.items_path = Path(self.temp_dir.name) / "items"
        self.items_path.mkdir(parents=True, exist_ok=True)

    def test_clean_db_removes_orphans_and_unused_folders(self):
        from api.management.commands import cleandb

        item_keep = api_models.Item.objects.create(
            state=int(api_models.FileState.Complete),
            label="keep",
            filetype=int(api_models.FileType.Image),
            width=10,
            height=10,
        )
        item_missing = api_models.Item.objects.create(
            state=int(api_models.FileState.Complete),
            label="missing",
            filetype=int(api_models.FileType.Image),
            width=10,
            height=10,
        )

        keep_path = Path(item_keep.getpath())
        keep_path.parent.mkdir(parents=True, exist_ok=True)
        keep_path.write_bytes(b"")

        unused_folder = self.items_path / "unused"
        unused_folder.mkdir(parents=True, exist_ok=True)

        api_models.Rules.objects.create(
            label="keep",
            tag_name="source",
            tag_value="external",
        )
        api_models.Rules.objects.create(
            label="missing",
            tag_name="source",
            tag_value="external",
        )

        with patch.object(cleandb, "ITEMS_PATH", str(self.items_path)):
            result = cleandb.clean_db()

        self.assertTrue(result)
        self.assertFalse(api_models.Item.objects.filter(id=item_missing.id).exists())
        self.assertTrue(api_models.Item.objects.filter(id=item_keep.id).exists())
        self.assertFalse(unused_folder.exists())
        self.assertFalse(api_models.Rules.objects.filter(label="missing").exists())
        self.assertTrue(api_models.Rules.objects.filter(label="keep").exists())


class WatchdogListenerTests(TestCase):
    def _import_watchdog_listener(self):
        dummy_views_extension = types.ModuleType("api.views_extension")

        def edit_item(*args, **kwargs):
            return None

        def get_dimensions(*args, **kwargs):
            return (10, 10)

        def upload_item(*args, **kwargs):
            return None

        class VideoRemover:
            @staticmethod
            def process():
                return None

        dummy_views_extension.edit_item = edit_item
        dummy_views_extension.get_dimensions = get_dimensions
        dummy_views_extension.upload_item = upload_item
        dummy_views_extension.VideoRemover = VideoRemover

        with patch.dict(sys.modules, {"api.views_extension": dummy_views_extension}):
            if "api.management.commands.watchdog_listener" in sys.modules:
                del sys.modules["api.management.commands.watchdog_listener"]
            return importlib.import_module("api.management.commands.watchdog_listener")

    def test_event_processor_ignores_banned_filetypes(self):
        watchdog_listener = self._import_watchdog_listener()
        processor = watchdog_listener.EventProcessor()

        processor.add("C:/tmp/file.TMP", "created")
        self.assertEqual(processor.process_times, [])
        self.assertEqual(processor.file_assignments, {})

    def test_handle_delete_removes_missing_item(self):
        watchdog_listener = self._import_watchdog_listener()

        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        old_media_path = api_models.MEDIA_PATH
        api_models.MEDIA_PATH = temp_dir.name
        self.addCleanup(setattr, api_models, "MEDIA_PATH", old_media_path)

        item = api_models.Item.objects.create(
            state=int(api_models.FileState.NeedsLabel),
            label="",
            filetype=int(api_models.FileType.Image),
            width=10,
            height=10,
        )

        path = item.getpath()
        processor = watchdog_listener.EventProcessor()
        processor.handle_delete(path)

        self.assertFalse(api_models.Item.objects.filter(id=item.id).exists())

    def test_read_directory_calls_handle_check(self):
        watchdog_listener = self._import_watchdog_listener()
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        base = Path(temp_dir.name)
        (base / "ok.png").write_bytes(b"data")
        (base / "ignore.dropbox").write_bytes(b"data")

        with patch.object(
            watchdog_listener.EventProcessor, "handle_check"
        ) as handle_check:
            watchdog_listener.read_directory(str(base))

        handle_check.assert_called_once()
