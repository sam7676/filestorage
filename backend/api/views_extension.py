from moviepy.video.io.VideoFileClip import VideoFileClip
from django.core.files.uploadedfile import InMemoryUploadedFile, TemporaryUploadedFile
from django.core.files.storage import FileSystemStorage
from functools import reduce
import operator
from django.db.models import Q
from collections import defaultdict
from PIL import ImageFile, Image
import numpy as np
import base64
import io
import random
from heapq import heappush, heappop
from api.models import (
    Item,
    FileState,
    FileType,
    create_item,
    Tags,
    get_file_properties,
    Rules,
    TagConditions,
)
import os
from api.utils.process_images import (
    get_crop_image_and_bounds,
    crop_and_resize_image,
    apply_rgb_curves,
    rotate_image_90,
    MEDIA_HEIGHT,
)
from api.utils.key_paths import UNPROCESSED_PATH
import torch
from transformers import CLIPProcessor, CLIPModel
from pathlib import Path
from api.utils.overrides import add_tag_override
from collections import deque

TAG_STYLE_OPTIONS = (
    TagConditions.Is.value,
    TagConditions.IsNot.value,
    TagConditions.Contains.value,
    TagConditions.DoesNotContain.value,
    TagConditions.IsNull.value,
    TagConditions.IsNotNull.value,
)

DEFAULT_THUMBNAIL_SIZE = 200
THUMBNAIL_CACHE_SIZE = 1000


def get_next_crop_item(crop_max_height):
    item = Item.objects.all().filter(state=0).first()

    if not item:
        return None

    image, bounds = get_crop_image_and_bounds(item.getpath(), crop_max_height)

    return image, bounds, item.id


def get_next_tag_item(else_tag_random=False):
    item = (
        Item.objects.all()
        .filter(state=int(FileState.NeedsTags))
        .order_by("label", "id")
        .first()
    )

    if not item:
        if else_tag_random:
            items = Item.objects.all().filter(state__gt=int(FileState.NeedsTags))
            item = random.choice(items)
        else:
            return None

    return item.id


def crop_and_resize_from_view(
    item_id,
    rendered_size,  # (width, height)
    crop,  # (x1, x2, y1, y2)
    new_state,
    save_or_new="save",
    alpha=0.0,
    rotate_degrees=0,
):
    item = Item.objects.all().filter(id=item_id).get()

    old_path = item.getpath()
    base_image = Image.open(old_path)

    # Our image is displayed with size `rendered_width` * `rendered_height` and we pick up the crop region from that
    # Therefore, we must resize the crop region to represent the image's true size

    rendered_width, rendered_height = rendered_size

    width_ratio = base_image.width / rendered_width
    height_ratio = base_image.height / rendered_height

    x1, x2, y1, y2 = crop

    x1, x2 = x1 * width_ratio, x2 * width_ratio
    y1, y2 = y1 * height_ratio, y2 * height_ratio

    resized_image = crop_and_resize_image(base_image, corners=(x1, x2, y1, y2))
    resized_image = apply_rgb_curves(resized_image, alpha)
    if rotate_degrees:
        resized_image = rotate_image_90(resized_image, turns=rotate_degrees // 90)

    if save_or_new == "save":
        resized_image.save(old_path)

        edit_item(
            item_id=item_id,
            new_state=new_state,
            new_width=resized_image.width,
            new_height=resized_image.height,
        )

    elif save_or_new == "new":
        state = new_state
        width = resized_image.width
        height = resized_image.height
        filetype = int(FileType.Image)
        label = ""

        new_item = create_item(
            label=label, state=state, width=width, filetype=filetype, height=height
        )

        Path(new_item.getpath()).parent.mkdir(parents=True, exist_ok=True)
        resized_image.save(new_item.getpath())

    else:
        raise Exception(f"Error: Save or new received value {save_or_new}")


def delete_items(item_ids):
    for item_id in item_ids:
        item = Item.objects.all().filter(id=item_id).get()
        item_path = item.getpath()

        if os.path.exists(item_path):
            os.remove(item_path)

        item.delete()


def delete_items_desktop(item_ids):
    for item_id in item_ids:
        item = Item.objects.all().filter(id=item_id).get()
        if item.filetype == int(FileType.Video):
            VideoRemover.remove_video(item.id)
        else:
            item_path = item.getpath()

            if os.path.exists(item_path):
                os.remove(item_path)

            item.delete()


def item_data(item):
    return item.id, {
        "id": item.id,
        "filetype": item.filetype,
        "mime_type": "image/png"
        if item.filetype == int(FileType.Image)
        else "video/mp4",
        "path": item.getpath(),
        "width": item.width,
        "height": item.height,
        "state": item.state,
        "label": item.label,
    }


def get_items_and_paths_from_tags(tags, order_by=None):
    response_results = {}

    objects = Item.objects.all()

    for z, tagList in tags.items():
        tagName, tagCondition = z

        if tagName == "id":
            if tagCondition == TagConditions.Is.value:
                objects = objects.filter(id__in=tagList)
            elif tagCondition == TagConditions.IsNot.value:
                objects = objects.exclude(id__in=tagList)

        elif tagName == "state":
            state_map = {
                "uncropped": int(FileState.NeedsCrop),
                "needscrop": int(FileState.NeedsCrop),
                "unmodified": int(FileState.NeedsModify),
                "needsmodify": int(FileState.NeedsModify),
                "unlabelled": int(FileState.NeedsLabel),
                "needslabel": int(FileState.NeedsLabel),
                "needstags": int(FileState.NeedsTags),
                "needsclip": int(FileState.NeedsClip),
                "complete": int(FileState.Complete),
            }

            # Preprocessing
            for i, tag in enumerate(tagList):
                if isinstance(tag, str):
                    if tag.isdigit():
                        tagList[i] = int(tag)
                    else:
                        tagList[i] = state_map[tag]

            if tagCondition == TagConditions.Is.value:
                objects = objects.filter(state__in=tagList)
            elif tagCondition == TagConditions.IsNot.value:
                objects = objects.exclude(state__in=tagList)

        elif tagName == "label":
            if tagCondition == TagConditions.Is.value:
                objects = objects.filter(
                    reduce(
                        operator.or_,
                        (
                            Q(label__in=tagList),
                            Q(tags__name="labelplus", tags__value__in=tagList),
                        ),
                    )
                )  # Labelplus support
            elif tagCondition == TagConditions.IsNot.value:
                objects = objects.exclude(label__in=tagList)
            elif tagCondition == TagConditions.Contains.value:
                objects = objects.filter(
                    reduce(operator.or_, (Q(label__contains=t) for t in tagList))
                )
            elif tagCondition == TagConditions.DoesNotContain.value:
                objects = objects.exclude(
                    reduce(operator.or_, (Q(label__contains=t) for t in tagList))
                )
            elif tagCondition == TagConditions.IsNull.value:
                objects = objects.filter(label__isnull=True)
            elif tagCondition == TagConditions.IsNotNull.value:
                objects = objects.filter(label__isnull=False)

        elif tagName == "filetype":
            filetype_map = {
                "image": int(FileType.Image),
                "video": int(FileType.Video),
                "images": int(FileType.Image),
                "videos": int(FileType.Video),
            }

            tagList = [filetype_map.get(tag, tag) for tag in tagList]

            if tagCondition == TagConditions.Is.value:
                objects = objects.filter(filetype__in=tagList)
            elif tagCondition == TagConditions.IsNot.value:
                objects = objects.exclude(filetype__in=tagList)
            elif tagCondition == TagConditions.Contains.value:
                objects = objects.filter(
                    reduce(operator.or_, (Q(filetype__contains=t) for t in tagList))
                )
            elif tagCondition == TagConditions.DoesNotContain.value:
                objects = objects.exclude(
                    reduce(operator.or_, (Q(filetype__contains=t) for t in tagList))
                )
            elif tagCondition == TagConditions.IsNull.value:
                objects = objects.filter(filetype__isnull=True)
            elif tagCondition == TagConditions.IsNotNull.value:
                objects = objects.filter(filetype__isnull=False)

        elif tagName == "width":
            # Cannot have multiple widths
            if len(tagList) != 1:
                continue

            # If using "is", take items where item.width >= provided_width
            # Reverse for "is not"

            if tagCondition == TagConditions.Is.value:
                objects = objects.filter(width__gte=tagList[0])
            if tagCondition == TagConditions.IsNot.value:
                objects = objects.filter(width__lt=tagList[0])

        else:
            # Generic tags
            if tagCondition == TagConditions.Is.value:
                objects = objects.filter(tags__name=tagName, tags__value__in=tagList)
            elif tagCondition == TagConditions.IsNot.value:
                objects = objects.exclude(tags__name=tagName, tags__value__in=tagList)
            elif tagCondition == TagConditions.Contains.value:
                objects = objects.filter(
                    reduce(
                        operator.or_,
                        (
                            Q(tags__name=tagName, tags__value__contains=t)
                            for t in tagList
                        ),
                    )
                )
            elif tagCondition == TagConditions.DoesNotContain.value:
                objects = objects.exclude(
                    reduce(
                        operator.or_,
                        (
                            Q(tags__name=tagName, tags__value__contains=t)
                            for t in tagList
                        ),
                    )
                )
            elif tagCondition == TagConditions.IsNull.value:
                objects = objects.filter(tags__name=tagName, tags__value__isnull=True)
            elif tagCondition == TagConditions.IsNotNull.value:
                objects = objects.exclude(tags__name=tagName)

    if order_by is not None:
        objects = objects.order_by(*order_by)

    for item in objects:
        item_id, item_info = item_data(item)

        response_results[item_id] = item_info

    return response_results


def add_tags(id_to_tag_dictionary):
    """
    Takes data of the form:
    {
    item_id_1: {
            tag_name_1: [tag_value_1, tag_value_2, ],
            tag_name_2: [tag_value_3, tag_value_4, ],
        },
    item_id_2: {
            tag_name_3: [tag_value_5, tag_value_6, ],
            tag_name_4: [tag_value_7, tag_value_8, ],
        },
    }
    """

    id_to_tag_dictionary = add_tag_override(id_to_tag_dictionary)

    for item_id, tag_dict in id_to_tag_dictionary.items():
        for tag_name, tag_values in tag_dict.items():
            # Can't add these tags
            if tag_name in ("state", "label", "filetype"):
                raise Exception(f"Tag forbidden: {tag_name} {tag_values}")

            for value in tag_values:
                # Only add tag if it doesn't exist already
                if (
                    len(
                        Item.objects.filter(
                            id=item_id, tags__name=tag_name, tags__value=value
                        )
                    )
                    > 0
                ):
                    continue
                Tags.objects.create(
                    item_id=Item.objects.filter(id=item_id).get(),
                    name=tag_name,
                    value=value,
                )


def remove_tags(id_to_tag_dictionary):
    """
    Takes data of the form:
    {
    item_id_1: {
            tag_name_1: [tag_value_1, tag_value_2, ],
            tag_name_2: [tag_value_3, tag_value_4, ],
        },
    item_id_2: {
            tag_name_3: [tag_value_5, tag_value_6, ],
            tag_name_4: [tag_value_7, tag_value_8, ],
        },
    }
    """
    for item_id, tag_dict in id_to_tag_dictionary.items():
        for tag_name, tag_values in tag_dict.items():
            if tag_name in ("state", "label", "filetype"):
                raise Exception(f"Tag forbidden: {tag_name} {tag_values}")

            for value in tag_values:
                tag_item = Tags.objects.filter(
                    item_id=item_id, name=tag_name, value=value
                )
                tag_item.delete()


def edit_item(item_id, new_state=None, new_label=None, new_width=None, new_height=None):
    item = Item.objects.all().filter(id=item_id).get()

    # If the embedding already exists, and the width or height has changed, or we are in the needsmodify state, we re-embed the item
    if (
        (new_width is not None and new_width != item.width)
        or (new_height is not None and new_height != item.height)
        or item.state == int(FileState.NeedsModify)
    ) and item.embedding is not None:
        np_embedding = ClipModel.process_item(item.id)
        b64string = ClipModel.np_to_base64(np_embedding)
        item.embedding = b64string
        item.save()

    old_path = item.getpath()

    if new_state is not None:
        # If we're in a labelled state but there's no label, raise an exception
        if (
            new_state
            in (
                int(FileState.NeedsClip),
                int(FileState.NeedsTags),
                int(FileState.Complete),
            )
            and item.label == ""
            and new_label is None
        ):
            raise Exception(
                f"File state error: label not provided. {item.id} {item.state} {item.label} {new_state}"
            )

        # If we're moving to an unlabelled state, remove the label
        if new_state in (
            int(FileState.NeedsLabel),
            int(FileState.NeedsCrop),
            int(FileState.NeedsModify),
        ):
            new_label = ""

        item.state = new_state

    # Assign a labelplus label of the new label
    if new_label is not None:
        item.label = new_label
        if new_label != "":
            add_tags(
                {
                    item.id: {
                        "labelplus": [
                            new_label,
                        ]
                    }
                }
            )

    if new_width is not None:
        item.width = new_width

    if new_height is not None:
        item.height = new_height

    # If we find an incorrectly-sized image, resize it to the correct height. It should have already been embedded, and this is resize-agnostic.
    if (
        item.height != MEDIA_HEIGHT
        and item.filetype == int(FileType.Image)
        and item.state >= int(FileState.NeedsClip)
    ):
        resize_path = old_path if os.path.exists(old_path) else item.getpath()
        image = Image.open(resize_path)

        new_width = int(image.width * MEDIA_HEIGHT / image.height)

        image = image.resize((new_width, MEDIA_HEIGHT))

        image.save(resize_path)

        item.height = MEDIA_HEIGHT
        item.width = new_width

    item.save()
    new_path = item.getpath()

    # Creating new folder if needed
    if not os.path.exists(item.getparent()):
        os.makedirs(item.getparent())

    if old_path != new_path and os.path.exists(old_path):
        os.rename(old_path, new_path)

    apply_rules(item.id)


def upload_item(path):
    properties = get_file_properties(path)
    if properties["type"] == int(FileType.Image):
        upload_image(path)
    elif properties["type"] == int(FileType.Video):
        upload_video(path)
    else:
        raise Exception(f"Error: property type {properties['type']} not recogniseed")


def upload_image(image):
    old_path = None

    # If the image is a path
    if isinstance(image, str):
        old_path = image
        image = Image.open(image)

    state = int(FileState.NeedsCrop)
    width, height = get_dimensions(image)

    filetype = int(FileType.Image)
    label = ""

    item = create_item(
        label=label, state=state, width=width, filetype=filetype, height=height
    )

    if old_path is not None:
        image.close()
        parent = Path(item.getpath()).parent
        os.makedirs(parent, exist_ok=True)
        os.rename(old_path, item.getpath())
    else:
        image.save(item.getpath())


def upload_video(video_object):
    # If the video is a path
    if isinstance(video_object, str):
        old_path = video_object
    elif type(video_object) in (InMemoryUploadedFile, TemporaryUploadedFile):
        # Save to unprocessed
        old_path = f"{UNPROCESSED_PATH}/{video_object.name}"
        FileSystemStorage(location=f"{UNPROCESSED_PATH}").save(
            video_object.name, video_object
        )
    else:
        print(f"Warning: videeo uploaded with unrecognised type: {type(video_object)}")

    video = VideoFileClip(old_path)
    try:
        state = int(FileState.NeedsLabel)
        width, height = get_dimensions(video)
        filetype = int(FileType.Video)
        label = ""
    finally:
        video.close()

    item = create_item(
        label=label, state=state, width=width, filetype=filetype, height=height
    )

    parent = Path(item.getpath()).parent
    os.makedirs(parent, exist_ok=True)
    os.rename(old_path, item.getpath())


def get_dimensions(item):
    needs_closing = False

    # We've been given a path, change it to the relevant object
    if isinstance(item, str):
        properties = get_file_properties(item)

        if properties["type"] == 0:
            item = Image.open(item)
        elif properties["type"] == 1:
            item = VideoFileClip(item)

        needs_closing = True

    if issubclass(type(item), ImageFile.ImageFile):
        w, h = item.width, item.height

    elif issubclass(type(item), VideoFileClip):
        w, h = item.w, item.h

    else:
        raise Exception(f"Item type not recognised: {type(item)}")

    if needs_closing:
        item.close()

    return w, h


def get_all_labels():
    return Item.objects.values("label").distinct().order_by("label")


def get_top_x_unlabelled_ids(x):
    return [
        item["id"]
        for item in Item.objects.filter(state=int(FileState.NeedsLabel))
        .order_by("id")[:x]
        .values("id")
    ]


def get_top_x_needsmodify_ids(x):
    return [
        item["id"]
        for item in Item.objects.filter(state=int(FileState.NeedsModify))
        .order_by("id")[:x]
        .values("id")
    ]


def get_untagged_ids(tag_name, tags_dict):
    # IDs where they are untagged w.r.t the tag name and satisfying constraints in tags_dict
    tags = defaultdict(list)

    for nv, condition in tags_dict.items():
        name, value = nv

        tags[(name, condition)].append(value)

    # Excludes objects where the tag name already exists
    # Not sure how this works.
    tags[(tag_name, TagConditions.IsNotNull.value)] += ["1"]

    tags[("state", TagConditions.Is.value)] += [
        int(FileState.NeedsClip),
        int(FileState.NeedsTags),
        int(FileState.Complete),
    ]

    data = get_items_and_paths_from_tags(tags, order_by=("label", "id"))

    data = [(k, v) for k, v in data.items()]
    data.sort(key=lambda x: x[0])
    data.sort(key=lambda x: x[1]["label"])

    return list(i[0] for i in data)


def get_thumbnail(item_id, width=DEFAULT_THUMBNAIL_SIZE, height=DEFAULT_THUMBNAIL_SIZE):
    item = Item.objects.all().filter(id=item_id).get()

    if item.filetype == int(FileType.Image):
        image = Image.open(item.getpath())
        image.thumbnail((width, height))

    elif item.filetype == int(FileType.Video):
        clip = VideoFileClip(item.getpath())
        try:
            frame = clip.get_frame(0.5)
            image = Image.fromarray(frame)
            image.thumbnail((width, height))
        finally:
            clip.close()

    return image


def get_tags(item_id):
    item = Item.objects.all().filter(id=item_id).get()
    filetype_map = {int(FileType.Image): "image", int(FileType.Video): "video"}

    tag_dct = {}

    tag_dct["label"] = [item.label]
    tag_dct["filetype"] = [filetype_map[item.filetype]]

    for tag in Tags.objects.filter(item_id=item_id).values("name", "value"):
        tag_dct[tag["name"]] = tag_dct.get(tag["name"], [])
        tag_dct[tag["name"]].append(tag["value"])

    return tag_dct


def get_tag(item_id, tag_name):
    item = Item.objects.all().filter(id=item_id).get()
    filetype_map = {int(FileType.Image): "image", int(FileType.Video): "video"}

    if tag_name == "label":
        return [item.label]
    if tag_name == "filetype":
        return [filetype_map[item.filetype]]
    if tag_name == "state":
        return [item.state]

    return list(
        sorted(
            [tag.value for tag in Tags.objects.filter(item_id=item_id, name=tag_name)]
        )
    )


def get_latest_confirmed_item(label):
    items = Item.objects.filter(
        state__in=[
            int(FileState.Complete),
        ],
        label=label,
    ).order_by("-id")[:20]

    if items:
        return [item.id for item in items]


def get_distinct_tags():
    return (
        Tags.objects.values("name", "value")
        .distinct()
        .order_by("-id", "name")
        .values_list("name", "value")
    )


def check_for_crops():
    return len(Item.objects.filter(state=int(FileState.NeedsCrop))) > 0


def check_for_modify():
    return len(Item.objects.filter(state=int(FileState.NeedsModify))) > 0


def check_for_unlabelled():
    return len(Item.objects.filter(state=int(FileState.NeedsLabel))) > 0


def check_for_clips():
    return len(Item.objects.filter(state=int(FileState.NeedsClip))) > 0


class ClipModel:
    model = None
    processor = None

    clip_model_name = "wkcn/TinyCLIP-ViT-8M-16-Text-3M-YFCC15M"
    device = "cpu"

    @classmethod
    def load_clip_model(cls):
        with torch.no_grad():
            model = CLIPModel.from_pretrained(cls.clip_model_name)
            processor = CLIPProcessor.from_pretrained(
                cls.clip_model_name, use_fast=True
            )

            model.eval()
            model.to(cls.device)

            cls.model = model
            cls.processor = processor

    @classmethod
    def get_clip_image_embedding(cls, image):
        if cls.model is None:
            cls.load_clip_model()

        import torch

        with torch.no_grad():
            # Preprocess
            inputs = cls.processor(
                images=image,
                return_tensors="pt",
            )

            # Move to device
            inputs = {k: v.to(cls.device) for k, v in inputs.items()}

            # Forward pass (no text, only image)
            outputs = cls.model.get_image_features(
                **inputs
            )  # shape: [1, embedding_dim]

            # Normalize to unit-length (common for CLIP embeddings)
            embeddings = outputs / outputs.norm(dim=-1, keepdim=True)

            # Convert to 1D CPU numpy array for storage / further processing
            return embeddings.squeeze(0).cpu().numpy()

    @staticmethod
    def compute_distance(embed1, embed2):
        return 1.0 - np.dot(embed1, embed2)

    @staticmethod
    def np_to_base64(np_array):
        buffer = io.BytesIO()
        np.save(buffer, np_array, allow_pickle=False)
        b64string = base64.b64encode(buffer.getvalue()).decode("utf-8")
        return b64string

    @staticmethod
    def base64_to_np(b64string):
        decoded_bytes = base64.b64decode(b64string)
        buffer = io.BytesIO(decoded_bytes)
        np_array = np.load(buffer, allow_pickle=False)
        return np_array

    @classmethod
    def process_item(cls, item_id):
        image = get_thumbnail(item_id, 224, 224)
        return cls.get_clip_image_embedding(image)

    @classmethod
    def process_unclipped_items(cls):
        items = Item.objects.filter(
            state__gte=int(FileState.NeedsClip), embedding__isnull=True
        )

        for item in items:
            embedding = ClipModel.process_item(item.id)
            b64string = ClipModel.np_to_base64(embedding)

            item.embedding = b64string
            item.save()

    @staticmethod
    def compute_advanced_distance(item_id1, item_id2, alpha=0.5):
        item1 = Item.objects.get(id=item_id1)
        item2 = Item.objects.get(id=item_id2)

        embedding_distance = ClipModel.compute_distance(
            ClipModel.base64_to_np(item1.embedding),
            ClipModel.base64_to_np(item2.embedding),
        )

        def tags_to_set(tagset):
            s = set()
            for key, val_list in tagset.items():
                for val in val_list:
                    s.add((key, val))

            return s

        tagset_1 = tags_to_set(get_tags(item1.id))
        tagset_2 = tags_to_set(get_tags(item2.id))

        tag_distance = 1 / (len(tagset_1.intersection(tagset_2)) + 1)

        return alpha * embedding_distance + (1 - alpha) * tag_distance


def get_next_clip_item():
    item = (
        Item.objects.all()
        .filter(state=int(FileState.NeedsClip))
        .order_by("label", "id")
        .first()
    )

    if not item:
        return None

    return item.id


def get_nearest_item(item_id, label, filetype):
    b64_embedding = Item.objects.get(id=item_id).embedding
    np_embedding = ClipModel.base64_to_np(b64_embedding)

    other_items = Item.objects.filter(label=label, filetype=filetype).exclude(
        id=item_id
    )

    nearest_item_id = -1
    smallest_distance = 2

    for other_item in other_items:
        if other_item.embedding is None:
            continue

        other_np_embedding = ClipModel.base64_to_np(other_item.embedding)

        distance = ClipModel.compute_distance(np_embedding, other_np_embedding)

        if distance < smallest_distance:
            nearest_item_id = other_item.id
            smallest_distance = distance

    return nearest_item_id


def apply_rules(item_id):
    item = Item.objects.get(id=item_id)
    tags_to_add = {}

    for rule in Rules.objects.filter(label=item.label):
        tags_to_add[rule.tag_name] = [rule.tag_value]

    add_tags({item.id: tags_to_add})


def get_random_compare_item():
    items = Item.objects.filter(state__in=[int(FileState.Complete)])
    return random.choice(items)


def get_comparison_items(item_id, num_items=10):
    item = Item.objects.get(id=item_id)
    distance_max_heap = []

    # 1: add any comparisons from class

    same_label_items = Item.objects.filter(label=item.label).exclude(id=item.id)

    nearest_item_id = -1
    smallest_distance = 2

    for other_item in same_label_items:
        if other_item.embedding is None:
            continue

        distance = ClipModel.compute_advanced_distance(
            item.id, other_item.id, alpha=0.3
        )

        if distance < smallest_distance:
            nearest_item_id = other_item.id
            smallest_distance = distance

    if nearest_item_id != -1:
        distance_max_heap.append((0, nearest_item_id))

    # 2: get at most K good comparisons

    global_items = Item.objects.exclude(
        id__in=[item.id] if nearest_item_id < 0 else [item.id, nearest_item_id]
    ).values_list("id", flat=True)
    global_items = list(global_items)
    random.shuffle(global_items)

    # Randomness and load speed
    global_items = global_items[:500]

    for global_item_id in global_items:
        global_item = Item.objects.get(id=global_item_id)

        if global_item.embedding is None:
            continue

        distance = ClipModel.compute_advanced_distance(
            item.id, global_item.id, alpha=0.2
        )

        if len(distance_max_heap) < num_items:
            heappush(distance_max_heap, (-distance, global_item.id))

        else:
            smallest_distance, smallest_id = distance_max_heap[0]
            smallest_distance = -smallest_distance

            if distance < smallest_distance:
                heappop(distance_max_heap)
                heappush(distance_max_heap, (-distance, global_item.id))

    return list(item_id for _, item_id in sorted(distance_max_heap))[::-1]


def start_file(item_id):
    os.startfile(Item.objects.get(id=item_id).getpath())


class ThumbnailCache:
    cache = {}
    cache_queue = deque()
    cache_size = THUMBNAIL_CACHE_SIZE

    @classmethod
    def __getitem__(cls, item_id):
        if item_id in cls.cache:
            return cls.cache[item_id]

        while len(cls.cache_queue) >= cls.cache_size:
            cls.cache.pop(cls.cache_queue.popleft())

        thumbnail = get_thumbnail(item_id)
        cls.cache[item_id] = thumbnail
        cls.cache_queue.append(item_id)
        return thumbnail


class VideoRemover:
    videos_to_remove = (
        deque()
    )  # used for thread safety, and same item throughout while keeping iteration smooth

    @classmethod
    def remove_video(cls, item_id):
        # Remove it from the database, and then repeatedly attempt to remove the item
        # Leaves dangling items, worst case these get picked up when re-running the desktop application

        item = Item.objects.get(id=item_id)

        cls.videos_to_remove.append(item.getpath())
        item.delete()

    @classmethod
    def process(cls):
        for _ in range(len(cls.videos_to_remove)):
            path = cls.videos_to_remove.popleft()
            if not os.path.exists(path):
                continue

            try:
                os.remove(path)
            except OSError:
                cls.videos_to_remove.append(path)


thumbnail_cache = ThumbnailCache()
