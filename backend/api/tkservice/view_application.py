from api.views_extension import (
    TagConditions,
    get_thumbnail,
    get_items_and_paths_from_tags,
    get_tag,
    get_tags,
    TAG_STYLE_OPTIONS,
    delete_items,
    edit_item,
)
from api.models import Item, FileType, FileState
import tkinter as tk
from PIL import ImageTk, Image
from tkvideo import tkvideo
from functools import partial
from collections import defaultdict
import random
import os

PAGE_WIDTH = 1100
PAGE_HEIGHT = 700


SORT_METRIC_OPTIONS = ("alphabetical", "random")

MODIFY_ITEMS_PAD_H = 16
MODIFY_ITEMS_MIN_W = 108


class ViewApp:
    def __init__(self):
        self.win = tk.Tk()
        self.win.state("zoomed")

        self.win_exists = True

        self.win.protocol("WM_DELETE_WINDOW", self.close_window)

        self.win.geometry("1920x1000+0+0")
        self.win.grid_rowconfigure(0, weight=1)
        self.win.grid_columnconfigure(0, weight=1)

        self.items_per_bin = 0
        self.items_per_window = 2
        self.page_increment_rate = 1
        self.max_bin_videos = 1

        self.item_ids = []
        self.id_data = {}
        # {
        #     "tk_label": None,
        #     "width": None,
        #     "height": None,
        #     "bin": None,
        #     "metric": None,
        #     "video_player": None,
        # }

        self.bins = defaultdict(list)
        # {
        #     "ids": [None, None],
        #     "width": None,
        #     "height": None,
        #     "video_count": 0,
        # }

        self.bin_group_metric = "label"
        self.sort_metric_option = "alphabetical"
        self.orderby_metric = "random"
        self.orderby_usenull = True
        self.modify_mode = False  # safety against deleting items
        self.thumbnail_mode = False  # for videos

        # (item_id, VideoPlayer)
        self.clear_video_players_set = set()

        self.chosen_tags = {
            ("state", "needsclip"): TagConditions.Is.value,
            ("state", "needstags"): TagConditions.Is.value,
            ("state", "complete"): TagConditions.Is.value,
            ("source", "internal"): TagConditions.IsNot.value,
            ("_", "_"): TagConditions.Is.value,
        }

        self.item_frame = tk.Frame()
        self.tag_frame = tk.Frame()

        self.current_page = 0
        self.max_page = 0

        self.get_ids_and_build_bins()

        self.win.bind("<Prior>", self.decrement_page)
        self.win.bind("<Next>", self.increment_page)
        self.win.bind("<Up>", self.decrement_page)
        self.win.bind("<Down>", self.increment_page)
        self.win.bind("<Left>", self.decrement_page)
        self.win.bind("<Right>", self.increment_page)

        self.win.bind("<Shift-Up>", self.decrement_page_person)
        self.win.bind("<Shift-Down>", self.increment_page_person)
        self.win.bind("<Shift-Left>", self.decrement_page_person)
        self.win.bind("<Shift-Right>", self.increment_page_person)

        self.win.bind("<MouseWheel>", self.on_mouse_wheel)
        self.win.bind("<F5>", self.random_page)
        self.win.bind("<Return>", self.random_page)

        while self.win_exists:
            self.clear_video_players()

            self.load_chosen_tags()
            self.load_items()

            self.win.mainloop()

        self.clear_video_players()

    def close_window(self):
        self.win.quit()
        self.win.destroy()

        self.win_exists = False

    def on_mouse_wheel(self, event=None):
        value = int(-1 * (event.delta / 120))
        for _ in range(abs(value)):
            if value > 0:
                self.increment_page()
            else:
                self.decrement_page()

    def get_widget(self, frame, item_id):
        if "video_player" in self.id_data[item_id]:
            self.id_data[item_id].pop("video_player")

        item = Item.objects.filter(id=item_id).get()

        new_width, new_height = self.get_new_size(item.width, item.height)

        if item.filetype == int(FileType.Image):
            image = Image.open(item.getpath())
            resized_image = image.resize((new_width, new_height))

            photo_image = ImageTk.PhotoImage(resized_image)

            label = tk.Label(master=frame, image=photo_image, width=new_width)
            label.photo = photo_image

            return label

        elif item.filetype == int(FileType.Video):
            if not self.thumbnail_mode:
                label = tk.Label(master=frame, width=new_width)

                player = tkvideo(
                    item.getpath(), label, loop=1, size=(new_width, new_height)
                )
                player.play()

                self.id_data[item_id]["video_player"] = player

                return label

            else:
                resized_image = get_thumbnail(item.id, new_width, new_height)

                photo_image = ImageTk.PhotoImage(resized_image)

                label = tk.Label(master=frame, image=photo_image, width=new_width)
                label.photo = photo_image

                return label

    def clear_video_players(self):
        for item_id, player in list(self.clear_video_players_set):
            if player.item_removed:
                self.clear_video_players_set.remove((item_id, player))

    def get_new_size(self, width, height):
        new_item_height = PAGE_HEIGHT // self.items_per_window - MODIFY_ITEMS_PAD_H

        new_width = int(round(width * new_item_height / height))
        new_height = new_item_height

        if new_width > PAGE_WIDTH:
            new_width = PAGE_WIDTH
            new_height = int(round(PAGE_WIDTH / new_width * new_height))

        return new_width, new_height

    def get_ids_and_build_bins(self):
        # Processing our tag query

        tags = defaultdict(list)

        for z, condition in self.chosen_tags.items():
            name, value = z

            tags[(name, condition)].append(value)

        # Inserting our "order by" tag
        if not self.orderby_usenull:
            tags[(self.orderby_metric, TagConditions.IsNotNull.value)].append("")

        data = get_items_and_paths_from_tags(tags)

        self.item_ids = list(data.keys())

        self.bins = defaultdict(list)

        ids = [item_id for item_id in self.item_ids]

        if self.orderby_metric != "id":
            if self.orderby_metric == "random":
                random.shuffle(ids)
            else:
                ids.sort(key=lambda x: get_tag(x, self.orderby_metric), reverse=True)

        for item_id in ids:
            item = Item.objects.filter(id=item_id).get()

            item_type = int(item.filetype)

            new_width, new_height = self.get_new_size(item.width, item.height)

            new_width = max(new_width, MODIFY_ITEMS_MIN_W)

            if self.bin_group_metric != "":
                tag_data = get_tags(item_id)

                if self.bin_group_metric not in tag_data:
                    continue

                metric = tag_data[self.bin_group_metric][0]
            else:
                metric = ""

            bin_placed = False
            for bin_obj in self.bins[metric]:
                if bin_obj["width"] + new_width <= PAGE_WIDTH:
                    if (
                        self.items_per_bin > 0
                        and len(bin_obj["ids"]) + 1 > self.items_per_bin
                    ):
                        continue
                    if self.max_bin_videos > 0 and not self.thumbnail_mode:
                        if (
                            item_type == int(FileType.Video)
                            and bin_obj["video_count"] + 1 > self.max_bin_videos
                        ):
                            continue

                    bin_obj["width"] += new_width
                    bin_obj["ids"].append(item_id)
                    bin_obj["video_count"] += item_type  # 1 if video else 0
                    bin_placed = True
                    break

            if not bin_placed:
                bin_obj = {
                    "width": new_width,
                    "ids": [item_id],
                    "metric": metric,
                    "video_count": item_type,  # 1 if video else 0
                }
                self.bins[metric].append(bin_obj)

            self.id_data[item_id] = {
                "tk_label": None,
                "width": new_width,
                "height": new_height,
                "metric": metric,
                "bin": bin_obj,
            }

        if self.sort_metric_option == "alphabetical":
            self.sorted_bin_metrics = list(sorted(self.bins.keys()))

        else:
            self.sorted_bin_metrics = list(self.bins.keys())
            random.shuffle(self.sorted_bin_metrics)

        self.page_data = []
        for m in self.sorted_bin_metrics:
            for i, b in enumerate(self.bins[m]):
                if self.orderby_metric == "random":
                    random.shuffle(b["ids"])

                self.page_data.append((m, i, b))

        self.max_page = len(self.page_data)
        self.current_page = min(
            self.current_page, self.max_page - self.items_per_window
        )
        self.current_page = max(0, self.current_page)

    def load_items(self):
        # Loading selected images

        for widget in self.item_frame.winfo_children():
            widget.destroy()

        self.max_page = len(self.page_data)
        self.current_page = min(
            self.current_page, self.max_page - self.items_per_window
        )
        self.current_page = max(0, self.current_page)

        self.item_frame = tk.Frame()
        self.item_frame.grid(row=0, column=0, sticky="ew")

        self.item_frame.rowconfigure(0, weight=1)
        self.item_frame.columnconfigure(0, weight=1)

        self.row_frame = tk.Frame(master=self.item_frame)
        self.row_frame.grid(row=0, column=0, sticky="ew")

        self.row_frame.columnconfigure(0, weight=1)

        # Build out our X rows
        # Place the bins accordingly on the rows

        for r in range(self.items_per_window):
            row_frame = tk.Frame(master=self.row_frame)
            row_frame.grid(row=r, column=0)

            self.row_frame.rowconfigure(r, weight=1)

            if r >= len(self.page_data):
                break

            metric, pos_in_metric, bin_obj = self.page_data[self.current_page + r]

            for j, item_id in enumerate(bin_obj["ids"]):
                tk_label_frame = tk.Frame(master=row_frame)
                tk_label_frame.grid(row=r, column=j)

                tk_button_frame = tk.Frame(master=tk_label_frame)
                tk_button_frame.grid(row=0, column=0)

                delete_button = tk.Button(
                    master=tk_button_frame,
                    text="X",
                    command=partial(self.delete_id, item_id),
                    width=1,
                    height=1,
                    font=("Arial", 5),
                    relief=tk.FLAT,
                )
                modify_button = tk.Button(
                    master=tk_button_frame,
                    text="M",
                    command=partial(self.modify_id, item_id),
                    width=1,
                    height=1,
                    font=("Arial", 5),
                    relief=tk.FLAT,
                )
                label_button = tk.Button(
                    master=tk_button_frame,
                    text="L",
                    command=partial(self.label_id, item_id),
                    width=1,
                    height=1,
                    font=("Arial", 5),
                    relief=tk.FLAT,
                )
                tag_button = tk.Button(
                    master=tk_button_frame,
                    text="T",
                    command=partial(self.tag_id, item_id),
                    width=1,
                    height=1,
                    font=("Arial", 5),
                    relief=tk.FLAT,
                )
                open_button = tk.Button(
                    master=tk_button_frame,
                    text="O",
                    command=partial(self.open_id, item_id),
                    width=1,
                    height=1,
                    font=("Arial", 5),
                    relief=tk.FLAT,
                )
                print_button = tk.Button(
                    master=tk_button_frame,
                    text="P",
                    command=partial(
                        print,
                        f"{item_id} {Item.objects.filter(id=item_id).get().label}",
                    ),
                    width=1,
                    height=1,
                    font=("Arial", 5),
                    relief=tk.FLAT,
                )

                delete_button.grid(row=0, column=0)
                modify_button.grid(row=0, column=1)
                label_button.grid(row=0, column=2)
                tag_button.grid(row=0, column=3)
                open_button.grid(row=0, column=4)
                print_button.grid(row=0, column=5)

                tk_label = self.get_widget(tk_label_frame, item_id)

                tk_label.grid(row=1, column=0)

            metric_label = tk.Label(
                master=self.row_frame,
                text=f"{metric} [{pos_in_metric + 1}/{len(self.bins[metric])}]",
                font=("Arial", 5),
            )
            metric_label.grid(row=r, column=1, sticky="e")

        self.page_frame = tk.Frame(master=self.item_frame)
        self.page_frame.grid(row=1, column=0)

        super_previous_button = tk.Button(
            master=self.page_frame,
            text="<<",
            command=self.decrement_page_person,
            relief=tk.GROOVE,
            width=2,
        )
        previous_button = tk.Button(
            master=self.page_frame,
            text="<",
            command=self.decrement_page,
            relief=tk.GROOVE,
            width=2,
        )
        current_label = tk.Button(
            master=self.page_frame,
            text=f"{self.current_page + 1 if self.max_page > 0 else 0} / {self.max_page - self.items_per_window + 1 if self.max_page > 0 else 0}",
            relief=tk.GROOVE,
            width=8,
        )
        next_button = tk.Button(
            master=self.page_frame,
            text=">",
            command=self.increment_page,
            relief=tk.GROOVE,
            width=2,
        )
        super_next_button = tk.Button(
            master=self.page_frame,
            text=">>",
            command=self.increment_page_person,
            relief=tk.GROOVE,
            width=2,
        )

        super_previous_button.grid(row=0, column=0)
        previous_button.grid(row=0, column=1)
        current_label.grid(row=0, column=2)
        next_button.grid(row=0, column=3)
        super_next_button.grid(row=0, column=4)

    def load_chosen_tags(self):
        # Loading selected tags

        for widget in self.tag_frame.winfo_children():
            widget.destroy()

        self.tag_frame = tk.Frame()
        self.tag_frame.grid(row=0, column=1, sticky="nw")

        # Setting items per bin and items per window

        tag_options_frame = tk.Frame(master=self.tag_frame)
        tag_options_frame.grid(row=0, column=0, sticky="ew")

        tag_options_frame.rowconfigure(0, weight=1)
        tag_options_frame.columnconfigure(1, weight=1)

        data = (
            (
                "Bin size",
                self.modify_items_per_bin,
                self.items_per_bin,
                self.update_items_per_bin,
                self.items_per_bin if self.items_per_bin > 0 else "",
            ),
            (
                "Window size",
                self.modify_items_per_window,
                self.items_per_window,
                self.update_items_per_window,
                self.items_per_window,
            ),
            (
                "Page increment",
                self.modify_page_increment,
                self.page_increment_rate,
                self.update_page_increment,
                self.page_increment_rate,
            ),
            (
                "Video bin count",
                self.modify_video_bin_count,
                self.max_bin_videos,
                self.update_video_bin_count,
                self.max_bin_videos if self.max_bin_videos > 0 else "",
            ),
        )

        for i, z in enumerate(data):
            name, modify_fn, clear_value, update_fn, insert_txt = z

            i_label = tk.Label(master=tag_options_frame, text=name, width=11)
            i_label.grid(row=i, column=0)

            modify_buttons_frame = tk.Frame(master=tag_options_frame)
            modify_buttons_frame.grid(row=i, column=1)

            clear_button = tk.Button(
                master=modify_buttons_frame,
                text="x",
                command=partial(modify_fn, -clear_value),
            )
            clear_button.grid(row=0, column=1)

            decrement_button = tk.Button(
                master=modify_buttons_frame, text="-", command=partial(modify_fn, -1)
            )
            decrement_button.grid(row=0, column=2)

            items_entry = tk.Entry(master=modify_buttons_frame, width=3)
            items_entry.insert(0, insert_txt)
            items_entry.grid(row=0, column=3)

            increment_button = tk.Button(
                master=modify_buttons_frame, text="+", command=partial(modify_fn, 1)
            )
            increment_button.grid(row=0, column=4)

            update_button = tk.Button(
                master=modify_buttons_frame,
                text="=",
                command=partial(update_fn, items_entry),
            )
            update_button.grid(row=0, column=5)

        numeric_count = len(data)

        # Metric update

        metric_buttons_frame = tk.Frame(master=tag_options_frame)
        metric_buttons_frame.grid(row=numeric_count, column=1)

        metric_label = tk.Label(master=tag_options_frame, text="Metric", width=11)
        metric_label.grid(row=numeric_count, column=0)

        metric_remove_button = tk.Button(
            master=metric_buttons_frame, text="x", command=self.remove_bin_group_metric
        )
        metric_entry = tk.Entry(master=metric_buttons_frame, width=16)
        metric_entry.insert(0, self.bin_group_metric)
        metric_button = tk.Button(
            master=metric_buttons_frame,
            text="+",
            command=partial(self.update_bin_group_metric, metric_entry),
        )

        metric_remove_button.grid(row=0, column=1)
        metric_entry.grid(row=0, column=2)
        metric_button.grid(row=0, column=3)

        metric_orderby_frame = tk.Frame(master=tag_options_frame)
        metric_orderby_frame.grid(row=numeric_count + 1, column=1)

        orderby_label = tk.Label(master=tag_options_frame, text="Order by", width=11)
        orderby_label.grid(row=numeric_count + 1, column=0)

        orderby_clear = tk.Button(
            master=metric_orderby_frame, text="x", command=self.clear_orderby_metric
        )
        orderby_entry = tk.Entry(master=metric_orderby_frame, width=16)
        orderby_entry.insert(0, self.orderby_metric)
        orderby_button = tk.Button(
            master=metric_orderby_frame,
            text="¬",
            command=partial(self.update_orderby_metric, orderby_entry),
        )
        orderby_usenull_button = tk.Button(
            master=metric_orderby_frame,
            text="Use null",
            fg="green" if self.orderby_usenull else "red",
            command=self.update_orderby_usenull,
        )

        orderby_clear.grid(row=0, column=0)
        orderby_entry.grid(row=0, column=1)
        orderby_button.grid(row=0, column=2)
        orderby_usenull_button.grid(row=0, column=3)

        sortby_extra_frame = tk.Frame(master=tag_options_frame)
        sortby_extra_frame.grid(row=numeric_count + 2, column=1)

        sortby_label = tk.Label(master=tag_options_frame, text="Sort by", width=11)
        sortby_label.grid(row=numeric_count + 2, column=0)

        sortby_sv = tk.StringVar(value=self.sort_metric_option)

        sortby_dropdown = tk.OptionMenu(
            sortby_extra_frame, sortby_sv, *SORT_METRIC_OPTIONS
        )
        sortby_dropdown.config(width=15)

        sortby_update = tk.Button(
            master=sortby_extra_frame,
            text="+",
            command=partial(self.update_sort_metric, sortby_sv),
        )

        sortby_dropdown.grid(row=0, column=0)
        sortby_update.grid(row=0, column=1)

        search_label = tk.Label(master=tag_options_frame, text="Search", width=6)
        search_label.grid(row=numeric_count + 3, column=0)

        metric_search_frame = tk.Frame(master=tag_options_frame)
        metric_search_frame.grid(row=numeric_count + 3, column=1)

        search_entry = tk.Entry(master=metric_search_frame, width=16)
        search_button = tk.Button(
            master=metric_search_frame,
            text="¬",
            command=partial(self.search_for_page, search_entry),
        )

        search_entry.grid(row=0, column=0)
        search_button.grid(row=0, column=1)

        goto_label = tk.Label(master=tag_options_frame, text="Go to", width=6)
        goto_label.grid(row=numeric_count + 4, column=0)

        metric_goto_frame = tk.Frame(master=tag_options_frame)
        metric_goto_frame.grid(row=numeric_count + 4, column=1)

        goto_entry = tk.Entry(master=metric_goto_frame, width=16)
        goto_button = tk.Button(
            master=metric_goto_frame,
            text="¬",
            command=partial(self.goto_page, goto_entry),
        )

        goto_entry.grid(row=0, column=0)
        goto_button.grid(row=0, column=1)

        self.modify_mode_button = tk.Button(
            master=self.tag_frame,
            text="Modify mode",
            command=self.complete_modify_mode,
            fg="red" if self.modify_mode else "black",
        )
        self.modify_mode_button.grid(row=3, sticky="ew")

        self.thumbnail_mode_button = tk.Button(
            master=self.tag_frame,
            text="Thumbnail mode",
            command=self.toggle_thumbnail_mode,
            fg="red" if self.thumbnail_mode else "black",
        )
        self.thumbnail_mode_button.grid(row=4, sticky="ew")

        state_items = []
        filetype_items = []
        label_items = []
        other_items = []

        for k, v in sorted(self.chosen_tags.items()):
            tag_name, tag_value = k
            tag_style = v

            if tag_style == "state":
                state_items.append((k, v))
            elif tag_style == "filetype":
                filetype_items.append((k, v))
            elif tag_style == "label":
                label_items.append((k, v))
            else:
                other_items.append((k, v))

        items = (
            state_items
            + filetype_items
            + label_items
            + other_items
            + [(("", ""), TagConditions.Is.value)]
        )

        # Load current tags
        for i, z in enumerate(items):
            tag_name, tag_value = z[0]
            tag_style = z[1]

            row_frame = tk.Frame(master=self.tag_frame)
            row_frame.grid(row=i + numeric_count + 4)

            tag_name_entry = tk.Entry(row_frame, width=16)
            tag_name_entry.insert(0, tag_name)

            tag_style_sv = tk.StringVar(value=tag_style)

            tag_style_dropdown = tk.OptionMenu(
                row_frame, tag_style_sv, *TAG_STYLE_OPTIONS
            )
            tag_style_dropdown.config(width=8)

            tag_value_entry = tk.Entry(row_frame, width=16)
            tag_value_entry.insert(0, tag_value)

            update_tag_button = tk.Button(
                row_frame,
                text="+",
                command=partial(
                    self.update_tag,
                    name_entry=tag_name_entry,
                    style_sv=tag_style_sv,
                    value_entry=tag_value_entry,
                    old_name=tag_name,
                    old_style=tag_style,
                    old_value=tag_value,
                ),
            )

            delete_tag_button = tk.Button(
                row_frame,
                text="x",
                command=partial(
                    self.delete_tag, old_name=tag_name, old_value=tag_value
                ),
            )

            tag_name_entry.grid(row=i, column=0)
            tag_style_dropdown.grid(row=i, column=1)
            tag_value_entry.grid(row=i, column=2)

            update_tag_button.grid(row=i, column=3)
            delete_tag_button.grid(row=i, column=4)

    def update_tag(
        self, name_entry, style_sv, value_entry, old_name, old_style, old_value
    ):
        new_name = name_entry.get()
        new_style = style_sv.get()
        new_value = value_entry.get()

        new_name = new_name.strip().lower()
        new_value = new_value.strip().lower()

        if new_name == "" and new_value == "":
            self.delete_tag(old_name, old_value)

        else:
            if not (old_name == "" and old_value == ""):
                if (old_name, old_value) in self.chosen_tags:
                    self.chosen_tags.pop((old_name, old_value))
            self.chosen_tags[(new_name, new_value)] = new_style

            self.rebuild_and_reset()

    def delete_tag(self, old_name, old_value):
        if old_name == "" and old_value == "":
            return

        self.chosen_tags.pop((old_name, old_value))

        self.rebuild_and_reset()

    def update_items_per_bin(self, items_per_bin_entry, event=None):
        if items_per_bin_entry.get().isnumeric():
            value = int(items_per_bin_entry.get())
            value = max(0, value)
        else:
            value = 0

        self.items_per_bin = value

        self.rebuild_and_reset()

    def modify_items_per_bin(self, change, event=None):
        self.items_per_bin = max(0, self.items_per_bin + change)
        self.rebuild_and_reset()

    def update_items_per_window(self, items_per_window_entry, event=None):
        if items_per_window_entry.get().isnumeric():
            value = int(items_per_window_entry.get())
            value = max(1, value)
        else:
            value = 1

        self.items_per_window = value
        self.rebuild_and_reset()

    def modify_items_per_window(self, change, event=None):
        self.items_per_window = max(1, self.items_per_window + change)
        self.rebuild_and_reset()

    def update_page_increment(self, page_increment_entry, event=None):
        if page_increment_entry.get().isnumeric():
            value = int(page_increment_entry.get())
            value = max(1, value)
        else:
            value = 1

        self.page_increment_rate = value
        self.rebuild_and_reset()

    def update_video_bin_count(self, video_bin_entry, event=None):
        if video_bin_entry.get().isnumeric():
            value = int(video_bin_entry.get())
            value = max(0, value)
        else:
            value = 1

        self.max_bin_videos = value
        self.rebuild_and_reset()

    def modify_page_increment(self, change, event=None):
        self.page_increment_rate = max(1, self.page_increment_rate + change)
        self.rebuild_and_reset()

    def modify_video_bin_count(self, change, event=None):
        self.max_bin_videos = max(0, self.max_bin_videos + change)
        self.rebuild_and_reset()

    def update_bin_group_metric(self, bin_group_metric_entry, event=None):
        self.bin_group_metric = bin_group_metric_entry.get()

        self.rebuild_and_reset()

    def remove_bin_group_metric(self, event=None):
        self.bin_group_metric = ""

        self.rebuild_and_reset()

    def update_sort_metric(self, sort_metric_sv, event=None):
        self.sort_metric_option = sort_metric_sv.get()

        self.rebuild_and_reset()

    def update_orderby_metric(self, orderby_entry, event=None):
        value = orderby_entry.get().strip().lower()
        if value == self.orderby_metric:
            return

        if value == "":
            self.orderby_metric = "id"
        else:
            self.orderby_metric = value

        self.rebuild_and_reset()

    def clear_orderby_metric(self, event=None):
        self.orderby_metric = "id"
        self.rebuild_and_reset()

    def update_orderby_usenull(self, event=None):
        self.orderby_usenull = not self.orderby_usenull

        self.rebuild_and_reset()

    def clear_item_id_inplace(self, item_id, onclear, item_type):
        video_player = self.id_data[item_id].get("video_player", None)
        if video_player:
            video_player.stop()
            video_player.toggle_fn = onclear
            self.id_data[item_id].pop("video_player")

            # Queueing to clean up
            self.clear_video_players_set.add((item_id, video_player))

        relevant_bin = self.id_data[item_id]["bin"]
        width = self.id_data[item_id]["width"]

        relevant_bin["ids"].remove(item_id)
        relevant_bin["width"] -= width

        if len(relevant_bin["ids"]) == 0:
            metric = self.id_data[item_id]["metric"]

            for i, z in enumerate(self.page_data):
                _, _, b = z
                if b == relevant_bin:
                    self.page_data.pop(i)
                    break

            self.bins[metric].remove(relevant_bin)

            if len(self.bins[metric]) == 0:
                self.bins.pop(metric)

        self.item_ids.remove(item_id)
        self.id_data.pop(item_id)

        self.reset_items()

        if item_type == FileType.Image or self.thumbnail_mode:
            # Delete or modify the image as expected
            onclear()

    def delete_id(self, item_id, event=None):
        if self.modify_mode:
            item_type = Item.objects.get(id=item_id).filetype

            # For videos, queue with delete_items
            self.clear_item_id_inplace(
                item_id, onclear=partial(delete_items, {item_id}), item_type=item_type
            )

    def modify_id(self, item_id, event=None):
        if self.modify_mode:
            # Images can't be modified
            filetype = Item.objects.get(id=item_id).filetype

            if filetype == int(FileType.Video):
                return

            self.clear_item_id_inplace(
                item_id,
                item_type=filetype,
                onclear=partial(edit_item, item_id, new_state=FileState.NeedsModify),
            )

    def label_id(self, item_id, event=None):
        if self.modify_mode:
            self.clear_item_id_inplace(
                item_id,
                item_type=Item.objects.get(id=item_id).filetype,
                onclear=partial(edit_item, item_id, new_state=FileState.NeedsLabel),
            )

    def tag_id(self, item_id, event=None):
        if self.modify_mode:
            edit_item(item_id, new_state=FileState.NeedsTags)

    def open_id(self, item_id, event=None):
        path = Item.objects.get(id=item_id).getpath()
        os.startfile(path)

    def complete_modify_mode(self, event=None):
        self.modify_mode = not self.modify_mode

        self.modify_mode_button.config(fg="red" if self.modify_mode else "black")

    def toggle_thumbnail_mode(self, event=None):
        self.thumbnail_mode = not self.thumbnail_mode
        self.reset_items()

    def reset_all(self):
        for widget in self.tag_frame.winfo_children():
            widget.destroy()

        self.reset_items()

    def reset_items(self):
        for widget in self.item_frame.winfo_children():
            widget.destroy()

        self.win.quit()

    def rebuild_and_reset(self):
        self.get_ids_and_build_bins()

        self.reset_all()

    def random_page(self, event=None):
        if self.max_page <= self.items_per_window:
            self.current_page = 0
        else:
            self.current_page = random.randint(0, self.max_page - self.items_per_window)
        self.load_items()

    def decrement_page(self, event=None):
        self.current_page = max(self.current_page - self.page_increment_rate, 0)

        self.load_items()

    def increment_page(self, event=None):
        self.current_page = min(
            self.current_page + self.page_increment_rate,
            self.max_page - self.items_per_window,
        )
        self.load_items()

    def decrement_page_person(self, event=None):
        current_metric = self.page_data[self.current_page][0]

        for r in range(self.current_page - 1, -1, -1):
            metric = self.page_data[r][0]

            if metric != current_metric:
                self.current_page = r
                break

            else:
                self.current_page = r

        self.reset_items()

    def increment_page_person(self, event=None):
        current_metric = self.page_data[self.current_page][0]

        for r in range(self.current_page, self.max_page - self.items_per_window + 1):
            metric = self.page_data[r][0]

            if metric != current_metric:
                self.current_page = r
                break
            else:
                self.current_page = r

        self.reset_items()

    def search_for_page(self, search_entry, event=None):
        metric_value = search_entry.get()

        found_startswith = False

        for i in range(self.max_page - self.items_per_window + 1):
            metric = self.page_data[i][0]

            # If we have starts with, declare it but do not break
            if metric.startswith(metric_value) and not found_startswith:
                self.current_page = i
                found_startswith = True

            # If we have exact match, break
            if metric == metric_value:
                self.current_page = i
                break

        self.reset_items()

    def goto_page(self, goto_entry, event=None):
        value = int(goto_entry.get())
        self.current_page = min(value, self.max_page - self.items_per_window)
        self.current_page = max(self.current_page, 0)

        self.reset_items()


def start_view_application():
    ViewApp()


if __name__ == "__main__":
    start_view_application()
