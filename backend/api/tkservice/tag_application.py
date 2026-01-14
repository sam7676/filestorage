from api.views_extension import (
    get_next_tag_item,
    start_file,
    delete_items,
    edit_item,
    get_tags,
    get_latest_confirmed_item,
    TagConditions,
    get_items_and_paths_from_tags,
    add_tags,
    get_distinct_tags,
    remove_tags,
)
from api.models import Item, FileType, FileState
import tkinter as tk
from PIL import ImageTk, Image
from tkvideo import tkvideo
from functools import partial
from collections import defaultdict
from time import sleep
import os
from api.utils.overrides import PRIORITY_TAG_MAP, PRIORITY_COLORS

SCALE_CONSTANT = 2
FLOOR_DIVISION = 16
MAX_HEIGHT_IN_CROP = 750
TAG_QUERY_WIDTH = 0
ENTRY_WIDTH = 10
SCREEN_WIDTH = 1920

BANNED_TAGS = ("label", "filetype")

CONFIRMED_COLOR = "#00FF00"

COLOR_DATA = [
    ("black", "#000000", -3, 1),
    ("white", "#EEEEEE", -1, 2),
    ("grey", "#808080", -2, 1),
    ("red", "#FF0000", 1, 2),
    ("yellow", "#E1C223", 21, 2),
    ("blue", "#525DBE", 50, 2),
    ("green", "#1CE31C", 31, 2),
    ("orange", "#FF8000", 12, 2),
    ("purple", "#AE35AE", 65, 2),
    ("pink", "#FB8AC8", 9, 3),
    ("brown", "#593915", 17, 3),
    ("navy", "#000080", 53, 3),
    ("cream", "#FFFDD0", 90, 3),
    ("beige", "#F9BF79", 94, 3),
    ("burgundy", "#6E2525", 5, 3),
    ("olive", "#556B2F", 34, 3),
    ("teal", "#008080", 44, 4),
    ("salmon", "#FA8072", 7, 4),
    ("peach", "#FFDAB9", 14, 4),
    ("khaki", "#F0E68C", 26, 4),
    ("tan", "#D2B48C", 93, 4),
]
COLOR_DATA_NAMES = set([i[0] for i in COLOR_DATA])


class TagApp:
    def __init__(self, tag_random=False):
        self.win = tk.Tk()
        self.win.state("zoomed")

        self.win_exists = True
        self.win.protocol("WM_DELETE_WINDOW", self.close_window)

        self.win.geometry(f"{SCREEN_WIDTH}x1000+0+0")
        self.win.grid_rowconfigure(0, weight=1)
        self.win.grid_columnconfigure(0, weight=1)

        self.item_frame = tk.Frame(master=self.win, height=MAX_HEIGHT_IN_CROP)
        self.item_frame.grid(row=0, column=0, sticky="nse")

        self.tag_frame = tk.Frame(master=self.win, height=MAX_HEIGHT_IN_CROP, width=200)
        self.tag_frame.grid(row=0, column=1, sticky="nsw")

        self.win.bind("<Return>", self.confirm)
        self.win.bind("<Delete>", self.delete)
        self.win.bind("-", self.revoke_last)

        self.tag_query_width = TAG_QUERY_WIDTH
        self.widget_width = 0
        self.partials_to_execute = []
        self.last_id = None

        self.ids = [-1]

        old_item_id = None

        while self.ids:
            if not self.win_exists:
                break

            item_id = get_next_tag_item(tag_random)

            if item_id is not None:
                self.ids = [item_id]

                self.item_id = item_id

                if item_id == old_item_id:
                    self.load_tags()
                else:
                    self.load_item()

                old_item_id = item_id
                self.win.mainloop()

            else:
                self.ids = []

        if self.win_exists:
            self.close_window()

    def close_window(self):
        for widget in self.item_frame.winfo_children():
            widget.destroy()

        self.win.quit()
        self.win.destroy()

        self.win_exists = False

    def get_widget(self, frame):
        item = Item.objects.filter(id=self.item_id).get()

        new_width = int(round(item.width * MAX_HEIGHT_IN_CROP / item.height))
        new_height = MAX_HEIGHT_IN_CROP

        self.widget_width = new_width

        if new_width > MAX_HEIGHT_IN_CROP * 1.5:
            new_width = int(round(MAX_HEIGHT_IN_CROP * 1.5))
            new_height = int(round(new_width * item.height / item.width))

        if item.filetype == int(FileType.Image):
            image = Image.open(item.getpath())
            resized_image = image.resize((new_width, new_height))

            photo_image = ImageTk.PhotoImage(resized_image)

            label = tk.Button(
                master=frame,
                image=photo_image,
                width=new_width,
                command=partial(start_file, item.id),
                relief=tk.FLAT,
                borderwidth=0,
                highlightthickness=0,
                padx=0,
                pady=0,
            )
            label.image = photo_image

            return label

        elif item.filetype == int(FileType.Video):
            sleep(0.1)

            label = tk.Label(master=frame, width=new_width)

            player = tkvideo(
                item.getpath(), label, loop=1, size=(new_width, new_height)
            )
            player.play()

            return label

    def load_item(self):
        self.item_frame.rowconfigure(0, weight=1)

        item_label = self.get_widget(self.item_frame)
        item_label.grid(row=0, column=0, sticky="n")

        button_frame = tk.Frame(master=self.item_frame)
        button_frame.grid(row=1, column=0, sticky="s")

        delete_button = tk.Button(
            master=button_frame, text="Delete", command=self.delete, width=7
        )
        id_label_button = tk.Button(
            master=button_frame, text=f"{self.item_id}", width=7, command=self.open_item
        )
        confirm_button = tk.Button(
            master=button_frame, text="Confirm", command=self.confirm, width=8
        )

        delete_button.grid(row=0, column=0, sticky="sew")
        id_label_button.grid(row=0, column=1, sticky="sew")
        confirm_button.grid(row=0, column=2, sticky="sew")

        self.load_tags()

    def delete(self, event=None):
        delete_items(item_ids=(self.item_id,))

        self.last_id = None

        self.clear_commit_and_reset()

    def confirm(self, event=None):
        self.commit()

        edit_item(item_id=self.item_id, new_state=int(FileState.Complete))

        self.last_id = self.item_id

        self.reset()

    def load_tags(self):
        self.commit()

        for widget in self.tag_frame.winfo_children():
            widget.destroy()

        self.partials_to_execute = []

        provided_query_width = self.tag_query_width

        query_size = 105
        tag_label_width = 160
        small_colour_width = 20

        if provided_query_width == 0:
            # How many queries can we fit?
            # At minimum, we have the setup width (for the other tags) taking up 400 space ish

            initial_tag_setup_width = 400

            if SCREEN_WIDTH - self.widget_width < initial_tag_setup_width:
                provided_query_width = 2

            else:
                # If not this, anything else is free space
                space = SCREEN_WIDTH - self.widget_width

                provided_query_width = (space - tag_label_width) // query_size
                provided_query_width = max(2, provided_query_width)

        # Handling the colours
        colour_space = query_size * provided_query_width + tag_label_width

        # Attempt to fit all colours in with length 1 at minimum
        if small_colour_width * len(COLOR_DATA) <= colour_space - tag_label_width:
            # (small_colour_width + 6(s-1)) * len(COLOR_DATA) <= colour_space - tag_label_width

            provided_colour_size = 1
            while (small_colour_width + 6 * (provided_colour_size - 1)) * len(
                COLOR_DATA
            ) <= colour_space - tag_label_width:
                provided_colour_size += 1
            provided_colour_size -= 1

            expected_width = small_colour_width + 6 * (provided_colour_size - 1)

            provided_colour_width = (colour_space - tag_label_width) // (expected_width)
            can_fit_all_colours = True

        else:
            provided_colour_size = 1
            provided_colour_width = (
                colour_space - tag_label_width - query_size
            ) // small_colour_width
            can_fit_all_colours = False

        provided_query_width = int(provided_query_width)
        provided_colour_width = int(provided_colour_width)

        tag_main_frame = tk.Frame(master=self.tag_frame)
        tag_main_frame.grid(row=0, column=0, sticky="n")

        tag_suggested_frame = tk.Frame(master=self.tag_frame)
        tag_suggested_frame.grid(row=1, column=0, sticky="s")

        self.tag_frame.rowconfigure(0, weight=1)

        # Tag handling
        self.tags = get_tags(self.item_id)
        filetype = Item.objects.filter(id=self.item_id).get().filetype

        # Holding the current tags on display
        tag_name_value_pairs = []
        tag_names_set = set()

        for tag_name, tag_values in self.tags.items():
            for value in tag_values:
                if tag_name in BANNED_TAGS:
                    continue

                tag_name_value_pairs.append((tag_name, value))
                tag_names_set.add(tag_name)

        tag_name_value_pairs.sort(key=lambda x: x[0])

        for banned_tag in reversed(BANNED_TAGS):
            tag_name_value_pairs.insert(0, (banned_tag, self.tags[banned_tag][0]))

        tag_name_value_pairs.append(("", ""))

        for i, z in enumerate(tag_name_value_pairs):
            tag_name, tag_value = z

            row_frame = tk.Frame(master=tag_main_frame)
            row_frame.grid(row=i, column=0)

            tag_entry_name = tk.Entry(master=row_frame)
            tag_entry_name.insert(0, tag_name)
            tag_entry_name.grid(row=0, column=0)

            tag_entry_value = tk.Entry(master=row_frame)
            tag_entry_value.insert(0, tag_value)
            tag_entry_value.grid(row=0, column=1)

            empty_entry = EmptyEntry()

            if tag_name in BANNED_TAGS:
                tag_entry_submit = tk.Button(master=row_frame, command=None, width=2)
                tag_entry_remove = tk.Button(master=row_frame, command=None, width=2)
                tag_entry_duplicate = tk.Button(master=row_frame, command=None, width=2)

                if tag_name == "label" and filetype == int(FileType.Image):
                    tag_entry_submit.configure(
                        text="+",
                        command=partial(self.new_label, value_entry=tag_entry_value),
                    )

            else:
                partial_cmd = partial(
                    self.update_tags,
                    name_entry=tag_entry_name,
                    value_entry=tag_entry_value,
                    old_name=tag_name,
                    old_value=tag_value,
                    reset_tags=True,
                )

                tag_entry_submit = tk.Button(
                    master=row_frame, command=partial_cmd, text="+", width=2
                )
                tag_entry_remove = tk.Button(
                    master=row_frame,
                    command=partial(
                        self.update_tags,
                        name_entry=empty_entry,
                        value_entry=empty_entry,
                        old_name=tag_name,
                        old_value=tag_value,
                        reset_tags=True,
                    ),
                    text="x",
                    width=2,
                )
                tag_entry_duplicate = tk.Button(
                    master=row_frame,
                    command=partial(
                        self.duplicate_tags,
                        name_entry=tag_entry_name,
                        value_entry=tag_entry_value,
                    ),
                    text="d",
                    width=2,
                )

            tag_entry_submit.grid(row=0, column=2)
            tag_entry_remove.grid(row=0, column=3)
            tag_entry_duplicate.grid(row=0, column=4)

        # Suggested tags
        tags_to_display = defaultdict(dict)
        # {
        #     "values": [],
        #     "priority": 0,
        # }

        # latest confirmed item to pop up for category
        latest_label_ids = get_latest_confirmed_item(label=self.tags["label"][0])

        if latest_label_ids is not None:
            for latest_label_id in latest_label_ids:
                suggested_tags_d = get_tags(latest_label_id)
                for tag_name, tag_values in suggested_tags_d.items():
                    if tag_name in BANNED_TAGS or (
                        tag_name in tag_names_set and tag_name != "labelplus"
                    ):
                        continue
                    for value in tag_values:
                        if (tag_name, value) in tag_name_value_pairs:
                            continue

                        if tag_name not in tags_to_display:
                            tags_to_display[tag_name] = {
                                "values": [value],
                                "priority": PRIORITY_TAG_MAP.get(tag_name, 1),
                            }

                        elif (
                            len(tags_to_display[tag_name]["values"])
                            < provided_query_width
                            and value not in tags_to_display[tag_name]["values"]
                        ):
                            tags_to_display[tag_name]["values"].append(value)

        # Gets distinct tags and recent values

        latest_distinct = get_distinct_tags()
        for tag_name, value in latest_distinct:
            if tag_name in BANNED_TAGS or (
                tag_name in tag_names_set and tag_name != "labelplus"
            ):
                continue
            if (tag_name, value) in tag_name_value_pairs:
                continue

            if tag_name not in tags_to_display:
                tags_to_display[tag_name] = {
                    "values": [value],
                    "priority": PRIORITY_TAG_MAP.get(tag_name, 0),
                }

            elif (
                len(tags_to_display[tag_name]["values"]) < provided_query_width
                and value not in tags_to_display[tag_name]["values"]
            ):
                tags_to_display[tag_name]["values"].append(value)

        tag_items = [
            (name, tag["values"], tag["priority"])
            for name, tag in tags_to_display.items()
        ]
        tag_items.sort(key=lambda x: x[0])
        tag_items.sort(key=lambda x: x[2])

        tag_items.append(("", [], 0))
        tag_items.append(("", [], 0))

        # Intro set
        suggested_frame = tk.Frame(master=tag_suggested_frame)
        suggested_frame.grid(row=0, column=0)

        suggested_row = tk.Frame(master=suggested_frame)
        suggested_row.grid(row=0, column=0)

        suggested_label = tk.Label(
            master=suggested_row, text="Suggested", relief=tk.RAISED, width=14
        )
        suggested_label.grid(row=0, column=0)

        tag_width_entry = tk.Entry(master=suggested_row, width=6)
        tag_width_entry.insert(0, self.tag_query_width)
        tag_width_entry.grid(row=0, column=1)

        tag_width_submit = tk.Button(
            master=suggested_row,
            text="+",
            command=partial(self.set_tag_width, tag_width_entry),
            font=("Arial", 6),
        )
        tag_width_submit.grid(row=0, column=2)

        commit_row = tk.Frame(master=suggested_frame)
        commit_row.grid(row=1, column=0)

        commit_button = tk.Button(
            master=commit_row, text="Commit", command=self.commit_and_reload, width=10
        )
        commit_button.grid(row=0, column=0)

        clear_button = tk.Button(
            master=commit_row,
            text="Clear",
            command=self.clear_commit_and_reload,
            width=10,
        )
        clear_button.grid(row=0, column=1)

        colours = [i for i in COLOR_DATA]
        colours.sort(key=lambda x: x[3])
        colours.sort(key=lambda x: x[2])

        for i, z in enumerate(tag_items):
            tag_name, tag_values, priority = z

            row_frame = tk.Frame(master=tag_suggested_frame)
            row_frame.grid(row=i + 2, column=0, sticky="w")

            tag_entry_name = tk.Entry(master=row_frame)
            tag_entry_name.insert(0, tag_name)
            tag_entry_name.grid(row=0, column=0)

            if priority != 0:
                priority_fg, priority_bg = PRIORITY_COLORS[priority]
                tag_entry_name.config(fg=priority_fg)
                tag_entry_name.config(bg=priority_bg)

            # If dealing with colours, we load the colours themselves rather than the names (less width!)
            if all(v in COLOR_DATA_NAMES for v in tag_values):
                start_idx = 1

                if not can_fit_all_colours:
                    # First entry: for manual colour input

                    tag_entry_value = tk.Entry(master=row_frame, width=ENTRY_WIDTH)
                    tag_entry_value.insert(0, "")
                    tag_entry_value.grid(row=0, column=1)

                    partial_cmd = partial(
                        self.update_tags,
                        name_entry=tag_entry_name,
                        value_entry=tag_entry_value,
                        old_name="",
                        old_value="",
                        reset_tags=False,
                    )

                    tag_entry_submit = tk.Button(
                        master=row_frame,
                        text="",
                        width=1,
                        font=("Calibri", 6),
                        relief=tk.FLAT,
                    )

                    tag_entry_submit.configure(
                        command=partial(self.add_partial, partial_cmd, tag_entry_submit)
                    )
                    tag_entry_submit.grid(row=0, column=2)

                    start_idx = 3

                    colours.sort(key=lambda x: x[3])
                    colours = colours[:provided_colour_width]
                    colours.sort(key=lambda x: x[2])

                # Others: choose colours

                for j in range(len(colours)):
                    if j < len(colours):
                        tag_value = colours[j][0]
                        tag_color = colours[j][1]

                    else:
                        tag_value = ""
                        tag_color = "#FFFFFF"

                    tag_entry_value = tk.Entry(master=row_frame, width=ENTRY_WIDTH)
                    tag_entry_value.insert(0, tag_value)

                    partial_cmd = partial(
                        self.update_tags,
                        name_entry=tag_entry_name,
                        value_entry=tag_entry_value,
                        old_name="",
                        old_value="",
                        reset_tags=False,
                    )

                    tag_entry_submit = tk.Button(
                        master=row_frame,
                        text="",
                        width=provided_colour_size,
                        font=("Calibri", 6),
                        relief=tk.FLAT,
                    )

                    tag_entry_submit.configure(
                        command=partial(self.add_partial, partial_cmd, tag_entry_submit)
                    )

                    tag_entry_value.config(bg=tag_color)
                    tag_entry_submit.config(bg=tag_color)

                    tag_entry_submit.grid(row=0, column=j + start_idx)

            else:
                # Computing colours if all options fit in provided query width
                value_rank_dictionary = {}
                if len(tag_values) < provided_query_width:
                    sorted_vals = list(sorted(tag_values))
                    n = len(sorted_vals)

                    # Percentage red = (distance from 0) = min(0 + j, 0 - j)
                    # Percentage green = (distance from 1/3) = min(n/3 + j, n/3 - j)
                    # Percentage blue = (distance from 2/3)

                    for j, v in enumerate(sorted_vals):
                        # Want these to be percentages that sum to 1
                        # Can I be any further away than my current position?
                        # Furthest from any colour you can be is 0.5

                        red_distance = min(
                            abs(j - -n),
                            abs(j - 0),
                            abs(j - n),
                        ) / (0.5 * n)

                        green_distance = min(
                            abs(j - -2 * n / 3),
                            abs(j - n / 3),
                            abs(j - 4 * n / 3),
                        ) / (0.5 * n)

                        blue_distance = min(
                            abs(j - -n / 3),
                            abs(j - 2 * n / 3),
                            abs(j - 5 * n / 3),
                        ) / (0.5 * n)

                        red_percent = 1 - red_distance
                        green_percent = 1 - blue_distance
                        blue_percent = 1 - green_distance

                        bg = (
                            int(224 + 31 * red_percent),
                            int(224 + 31 * green_percent),
                            int(224 + 31 * blue_percent),
                        )
                        fg = (
                            int(32 + 127 * red_percent),
                            int(32 + 127 * green_percent),
                            int(32 + 127 * blue_percent),
                        )

                        bg = "#%02x%02x%02x" % bg
                        fg = "#%02x%02x%02x" % fg

                        value_rank_dictionary[(v, "bg")] = bg
                        value_rank_dictionary[(v, "fg")] = fg

                for j in range(provided_query_width):
                    if j >= len(tag_values):
                        tag_value = ""
                    else:
                        tag_value = tag_values[j]

                    tag_entry_value = tk.Entry(master=row_frame, width=ENTRY_WIDTH)
                    tag_entry_value.insert(0, tag_value)

                    tag_entry_value.grid(row=0, column=2 * j + 1)

                    partial_cmd = partial(
                        self.update_tags,
                        name_entry=tag_entry_name,
                        value_entry=tag_entry_value,
                        old_name="",
                        old_value="",
                        reset_tags=False,
                    )

                    tag_entry_submit = tk.Button(
                        master=row_frame,
                        text="",
                        width=1,
                        font=("Calibri", 6),
                        relief=tk.FLAT,
                    )

                    tag_entry_submit.configure(
                        command=partial(self.add_partial, partial_cmd, tag_entry_submit)
                    )

                    # on the last row, we provide an "add to all with label" button
                    if i == len(tag_items) - 1:
                        partial_cmd = partial(
                            self.update_tags_all,
                            name_entry=tag_entry_name,
                            value_entry=tag_entry_value,
                            old_name="",
                            old_value="",
                        )
                        tag_entry_submit.configure(text="a", command=partial_cmd)

                    elif (tag_value, "fg") in value_rank_dictionary:
                        tag_entry_value.config(
                            fg=value_rank_dictionary[(tag_value, "fg")],
                            bg=value_rank_dictionary[(tag_value, "bg")],
                        )
                        tag_entry_submit.config(
                            fg=value_rank_dictionary[(tag_value, "fg")],
                            bg=value_rank_dictionary[(tag_value, "bg")],
                        )

                    elif tag_value == "":
                        tag_entry_submit.config(bg="#FFFFFF")

                    tag_entry_submit.grid(row=0, column=2 * j + 2)

    def update_tags(
        self, name_entry, value_entry, old_name, old_value, reset_tags=True, event=None
    ):
        new_name = name_entry.get()
        new_value = value_entry.get()

        new_name = new_name.strip().lower()
        new_value = new_value.strip().lower()

        if old_name == new_name and old_value == new_value:
            return

        if old_name != "" and old_value != "":
            remove_tags({self.item_id: {old_name: [old_value]}})

        if new_name != "" and new_value != "":
            add_tags({self.item_id: {new_name: [new_value]}})

            # Extra: handling "any/none" add/removal

            for t in ("top", "bottom"):
                if new_name in (f"{t}color", f"{t}type") and new_value in (
                    "any",
                    "none",
                ):
                    add_tags(
                        {
                            self.item_id: {
                                f"{t}color": [new_value],
                                f"{t}type": [new_value],
                            }
                        }
                    )

        if reset_tags:
            self.load_tags()

    def update_tags_all(self, name_entry, value_entry, old_name, old_value, event=None):
        new_name = name_entry.get()
        new_value = value_entry.get()

        new_name = new_name.strip().lower()
        new_value = new_value.strip().lower()

        if old_name != "" or old_value != "":
            return

        if not (new_name != "" and new_value != ""):
            return

        item = Item.objects.filter(id=self.item_id).get()

        tags = {
            ("label", TagConditions.Is.value): [item.label],
            ("state", TagConditions.Is.value): [int(FileState.NeedsTags)],
        }

        data = get_items_and_paths_from_tags(tags)
        ids = data.keys()

        add_tags({item_id: {new_name: [new_value]} for item_id in ids})

        self.load_tags()

    def new_label(self, value_entry, event=None):
        new_value = value_entry.get().strip().lower()
        if new_value == "":
            return

        self.confirm()
        edit_item(self.item_id, new_label=new_value, new_state=int(FileState.NeedsTags))
        self.reset()

    def duplicate_tags(self, name_entry, value_entry, event=None):
        new_name = name_entry.get().strip().lower()
        new_value = value_entry.get().strip().lower()

        add_tags({self.item_id: {new_name: [new_value]}})

        self.load_tags()

    def set_tag_width(self, tag_width_entry, event=None):
        if tag_width_entry.get().isnumeric():
            value = int(tag_width_entry.get())
            value = max(0, value)
            self.tag_query_width = value
            self.load_tags()

    def reset(self):
        for widget in self.item_frame.winfo_children():
            widget.destroy()

        self.win.quit()

    def commit(self):
        for p in self.partials_to_execute:
            p()

        self.partials_to_execute = []

    def commit_and_reload(self):
        self.load_tags()  # commit built into reset

    def open_item(self):
        os.startfile(Item.objects.get(id=self.item_id).getpath())

    def clear_commit_and_reload(self):
        self.partials_to_execute = []
        self.load_tags()

    def clear_commit_and_reset(self):
        self.partials_to_execute = []
        self.reset()

    def add_partial(self, partial_fn, button, event=None):
        self.partials_to_execute.append(partial_fn)
        button.config(fg=CONFIRMED_COLOR, bg=CONFIRMED_COLOR, command=None)

    def revoke_last(self, event=None):
        if not self.last_id:
            return
        edit_item(self.last_id, new_state=int(FileState.NeedsTags))
        self.clear_commit_and_reset()


class EmptyEntry:
    def get(self):
        return ""


def start_tag_application(tag_random=False):
    TagApp(tag_random)


if __name__ == "__main__":
    start_tag_application()
