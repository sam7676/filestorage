from django.core.management.base import BaseCommand
from api.models import Item, FileState, Rules
from api.utils.key_paths import ITEMS_PATH
import os


class Command(BaseCommand):
    def handle(self, **options):
        clean_db()


def clean_db():
    for item in Item.objects.all():
        if not os.path.exists(item.getpath()):
            print(item.getpath())
            item.delete()

    distinct_labels = set(
        Item.objects.filter(
            state__in=[
                int(FileState.Complete),
                int(FileState.NeedsTags),
                int(FileState.NeedsClip),
            ]
        )
        .values_list("label", flat=True)
        .distinct()
    )

    if os.path.exists(ITEMS_PATH):
        subfolders = [(f.name, f.path) for f in os.scandir(ITEMS_PATH) if f.is_dir()]

        for sf_name, sf_path in subfolders:
            if sf_name not in distinct_labels:
                os.rmdir(sf_path)

    for rule in Rules.objects.all():
        if rule.label not in distinct_labels:
            rule.delete()

    return True
