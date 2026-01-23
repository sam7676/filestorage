from django.db import models
from enum import IntEnum
from api.utils.key_paths import MEDIA_PATH
from pathlib import Path


class FileState(IntEnum):
    NeedsCrop = 0
    NeedsModify = 1
    NeedsLabel = 2
    NeedsClip = 3
    NeedsTags = 4
    Complete = 5


class FileType(IntEnum):
    Image = 0
    Video = 1


class Item(models.Model):
    state = models.IntegerField()
    label = models.CharField(max_length=100)
    filetype = models.IntegerField()
    width = models.IntegerField()
    height = models.IntegerField()
    embedding = models.TextField(null=True)

    def __str__(self):
        return f"{self.label} {self.filetype} ({self.width}x{self.height})"

    def getpath(self):
        string_id = self.getstringid()

        state_map = {
            0: "uncropped",
            1: "needsmodify",
            2: "unlabelled",
            3: f"items/{self.label}",
            4: f"items/{self.label}",
            5: f"items/{self.label}",
        }

        filetype_extension = {0: ".png", 1: ".mp4"}

        return f"{MEDIA_PATH}/{state_map[self.state]}/{string_id}{filetype_extension[self.filetype]}"

    def getstringid(self):
        return str(self.id).zfill(10)

    def getparent(self):
        path = Path(self.getpath())
        return str(path.parent)


# Sort out tags and figure out inner joining
class Tags(models.Model):
    item_id = models.ForeignKey(Item, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    value = models.CharField(max_length=100)


def print_labelplus():
    labelplus_value_set = set(
        Tags.objects.filter(name="labelplus").values_list("value", flat=True)
    )
    label_value_set = set(Item.objects.values_list("label", flat=True))
    for i in sorted(labelplus_value_set):
        if i not in label_value_set:
            print(i)


# Auto-applying tags to labels
class Rules(models.Model):
    label = models.CharField(max_length=100)
    tag_name = models.CharField(max_length=100)
    tag_value = models.CharField(max_length=100)

def print_methods():
    print("""
    print_rules(label=None, tag_name=None, tag_value=None, tag_first=True)
    print_missing_rules(tag_name)
    add_rule(label, tag_name, tag_value)
    remove_rule(label, tag_name, tag_value)
    """)

def print_rules(label=None, tag_name=None, tag_value=None, tag_first=True):
    sort_list = ("tag_name", "label") if tag_first else ("label", "tag_name")

    rules = Rules.objects.all()
    if label:
        rules = rules.filter(label=label)
    if tag_name:
        rules = rules.filter(tag_name=tag_name)
    if tag_value:
        rules = rules.filter(tag_value=tag_value)

    for rule in rules.order_by(*sort_list):
        print(
            f"{rule.label.ljust(20)}: {rule.tag_name.rjust(20)} is {rule.tag_value.ljust(20)}"
        )


def print_missing_rules(tag_name):
    labels = Item.objects.filter(
        state__in=[
            int(FileState.Complete),
            int(FileState.NeedsTags),
            int(FileState.NeedsClip),
        ]
    ).values_list("label", flat=True)
    distinct_set = set()
    distinct_labels = []
    for label in reversed(labels):
        if label not in distinct_set:
            distinct_set.add(label)
            distinct_labels.append(label)

    for label in distinct_labels:
        if len(Rules.objects.filter(label=label, tag_name=tag_name)) == 0:
            print(label)


def add_rule(label, tag_name, tag_value):
    tag_name = tag_name.strip()
    tag_value = tag_value.strip()

    if (
        len(Rules.objects.filter(label=label, tag_name=tag_name, tag_value=tag_value))
        > 0
    ):
        return

    Rules.objects.create(
        label=label,
        tag_name=tag_name,
        tag_value=tag_value,
    )


def remove_rule(label, tag_name, tag_value):
    rules = Rules.objects.filter(label=label, tag_name=tag_name, tag_value=tag_value)
    for rule in rules:
        rule.delete()

    return len(rules) > 0


def create_item(label: str, filetype: int, state: int, width: int, height: int) -> int:
    item = Item.objects.create(
        filetype=filetype,
        label=label,
        state=state,
        width=width,
        height=height,
    )

    return item


def get_file_properties(path):
    local_path = path[len(MEDIA_PATH) :].replace("\\", "/").split("/")
    if local_path[0] == "":
        local_path.pop(0)

    try:
        item_name, item_type = local_path[-1].split(".")
    except ValueError as e:
        print(local_path)
        raise e

    item_type = item_type.lower()

    image_item_types = ("png", "gif", "jpg", "jpeg", "webp")
    video_item_types = ("mp4", "mov")

    item_type_map = {
        image_item_types: int(FileType.Image),
        video_item_types: int(FileType.Video),
    }

    new_item_type = None

    for types in item_type_map:
        if item_type in types:
            new_item_type = item_type_map[types]
            break

    if new_item_type is None:
        raise Exception(f"Error {item_type} not recogniseed")

    item_type = new_item_type

    category = local_path[0]

    label = "" if len(local_path) == 2 else local_path[1]

    return {
        "name": item_name,
        "type": item_type,
        "category": category,
        "label": label,
    }


def try_get_item(path):
    item = None
    properties = get_file_properties(path)
    if properties["name"].isdigit():
        item_id = int(properties["name"])
        try:
            item = Item.objects.get(id=item_id)
        except Item.DoesNotExist:
            pass
    return item, properties
