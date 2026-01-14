from api.views_extension import (
    check_for_crops,
    check_for_modify,
    check_for_unlabelled,
    get_all_labels,
    get_untagged_ids,
    TagConditions,
    TAG_STYLE_OPTIONS,
    get_thumbnail,
    add_tags,
)
import tkinter as tk
from PIL import ImageTk
from functools import partial
import math

ITEMS_PER_ROW = 5
ITEMS_PER_PAGE = 100


class MultitagApp:
    def __init__(self, tag_names=[]):
        self.win = tk.Tk()
        self.win.state("zoomed")

        self.win_exists = True
        self.win.protocol("WM_DELETE_WINDOW", self.close_window_manual)
        self.window_closed_manually = False

        self.win.geometry("1920x1000+0+0")
        self.win.grid_rowconfigure(0, weight=1)
        self.win.grid_columnconfigure(0, weight=1)

        self.tag_names = list(tag_names[:])
        if not self.tag_names:
            self.tag_names = [
                "",
            ]

        self.main_frame = tk.Frame()

        while self.tag_names and not any(
            (
                check_for_crops(),
                check_for_modify(),
                check_for_unlabelled(),
            )
        ):
            self.selected_ids = set()
            self.id_data = {}
            # {
            #     "selected": False,
            #     "batch_toggled": False,
            #     "buttons": {
            #         "check": None,
            #         "batch": None
            #     },
            # }

            self.tag_name = self.tag_names.pop(0)

            self.items_per_page = ITEMS_PER_PAGE

            self.chosen_tags = {}

            self.ids = [-1]

            self.scrollbar_y = None
            self.images_canvas = None
            self.main_frame = tk.Frame()

            while self.ids:
                if not self.win_exists:
                    break

                self.ids = get_untagged_ids(self.tag_name, self.chosen_tags)

                self.page = 0
                self.max_page = math.ceil(len(self.ids) / self.items_per_page)

                self.labels = [
                    item["label"] for item in get_all_labels() if item["label"] != ""
                ]
                self.labels.sort()

                if not self.ids:
                    break

                # Collecting basic data
                for item_id in self.ids:
                    if item_id in self.id_data:
                        continue

                    self.id_data[item_id] = {
                        "selected": False,
                        "batch_toggled": False,
                    }

                self.load()
                self.win.mainloop()

        self.close_window()

    def close_window(self):
        for widget in self.main_frame.winfo_children():
            widget.destroy()

        self.win.quit()
        try:
            self.win.destroy()
        except tk.TclError:
            pass

        self.win_exists = False

    def close_window_manual(self):
        self.window_closed_manually = True
        self.close_window()

    def load(self):
        self.main_frame = tk.Frame()
        self.main_frame.grid(row=0, column=0)

        left_frame = tk.Frame(self.main_frame)
        left_frame.grid(row=0, column=0)

        right_frame = tk.Frame(self.main_frame)
        right_frame.grid(row=0, column=1)
        right_frame.grid_rowconfigure(0, weight=1)
        right_frame.grid_columnconfigure(0, weight=1)

        # Selecting all or deselecting all

        select_all_or_none_frame = tk.Frame(left_frame)
        select_all_or_none_frame.grid(row=0, column=0)

        select_all_button = tk.Button(
            master=select_all_or_none_frame, text="✓ all", command=self.select_all
        )
        deselect_all_button = tk.Button(
            master=select_all_or_none_frame, text="✗ all", command=self.deselect_all
        )

        select_all_button.grid(row=0, column=0)
        deselect_all_button.grid(row=0, column=1)

        self.image_frame = tk.Frame(left_frame)
        self.image_frame.grid(row=1, column=0)

        page_frame = tk.Frame(master=left_frame)
        page_frame.grid(row=2, column=0)

        items_per_page_entry = tk.Entry(master=page_frame, width=5, font=("Arial", 8))
        items_per_page_button = tk.Button(
            master=page_frame,
            text="+",
            width=1,
            command=partial(self.update_items_per_page, items_per_page_entry),
            font=("Arial", 7),
        )
        items_per_page_entry.insert(0, self.items_per_page)

        items_per_page_button.grid(row=0, column=0)
        items_per_page_entry.grid(row=0, column=1)

        self.page_label = tk.Label(
            master=page_frame,
            text=f"{self.page + 1} / {self.max_page}" if self.max_page > 0 else "0 / 0",
        )
        self.page_label.grid(row=0, column=2)

        page_entry = tk.Entry(master=page_frame, width=5, font=("Arial", 8))
        page_button = tk.Button(
            master=page_frame,
            text="+",
            width=1,
            command=partial(self.update_page, page_entry),
            font=("Arial", 7),
        )

        page_entry.grid(row=0, column=3)
        page_button.grid(row=0, column=4)

        self.load_images()

        # Right frame

        taglabels_entries_frame = tk.Frame(master=right_frame)
        taglabels_entries_frame.grid(row=0, column=0)

        tagname_label = tk.Label(
            text="Tag name", master=taglabels_entries_frame, width=30, relief="groove"
        )
        tagname_label.grid(row=0, column=0, sticky="nw")

        tagname_entry_frame = tk.Frame(master=taglabels_entries_frame)
        tagname_entry_frame.grid(row=1, column=0)

        tagname_entry = tk.Entry(master=tagname_entry_frame, width=30)
        tagname_entry.insert(0, self.tag_name)
        tagname_entry.grid(row=1, column=0, sticky="nw")

        tagname_button = tk.Button(
            text="+",
            master=tagname_entry_frame,
            width=1,
            command=partial(self.edit_tagname, tagname_entry),
        )
        tagname_button.grid(row=1, column=1, sticky="nw")

        tagvalue_label = tk.Label(
            text="Tag value", master=taglabels_entries_frame, width=30, relief="groove"
        )
        tagvalue_label.grid(row=2, column=0, sticky="nw")

        tagvalue_entry_frame = tk.Frame(master=taglabels_entries_frame)
        tagvalue_entry_frame.grid(row=3, column=0)

        tagvalue_entry = tk.Entry(master=tagvalue_entry_frame, width=30)
        tagvalue_entry.grid(row=3, column=0, sticky="nw")

        tagvalue_button = tk.Button(
            text="✓",
            master=tagvalue_entry_frame,
            width=1,
            command=partial(self.add_tags, tagvalue_entry),
        )
        tagvalue_button.grid(row=3, column=1, sticky="nw")

        self.othertag_frame = tk.Frame(master=right_frame)
        self.othertag_frame.grid(row=1, column=0, sticky="nw")

        self.load_tags()

        self.win.bind("<Up>", self.decrement_page)
        self.win.bind("<Down>", self.increment_page)
        self.win.bind("<Left>", self.decrement_page)
        self.win.bind("<Right>", self.increment_page)

    def load_tags(self):
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

            row_frame = tk.Frame(master=self.othertag_frame)
            row_frame.grid(row=i + 4)

            tag_name_entry = tk.Entry(row_frame, width=10)
            tag_name_entry.insert(0, tag_name)

            tag_style_sv = tk.StringVar(value=tag_style)

            tag_style_dropdown = tk.OptionMenu(
                row_frame, tag_style_sv, *TAG_STYLE_OPTIONS
            )
            tag_style_dropdown.config(width=8)

            tag_value_entry = tk.Entry(row_frame, width=10)
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

    def load_images(self):
        # Clear existing widgets
        for widget in self.image_frame.winfo_children():
            widget.destroy()

        # Canvas

        self.canvas = tk.Canvas(self.image_frame, width=200 * ITEMS_PER_ROW, height=700)
        self.scrollbar_y = tk.Scrollbar(
            self.image_frame, orient="vertical", command=self.canvas.yview
        )

        self.image_frame_parent = self.image_frame

        self.images_frame = tk.Frame(self.canvas)
        self.images_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )

        self.canvas.create_window((0, 0), window=self.images_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar_y.set)

        # Pack scrollbars and canvas
        self.scrollbar_y.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.images_canvas = self.canvas
        self.images_canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        # Load page label
        self.page_label.configure(
            text=f"{self.page + 1} / {self.max_page}" if self.max_page > 0 else "0 / 0"
        )

        row_frames = []

        ids = self.ids[
            self.items_per_page * self.page : self.items_per_page * (self.page + 1)
        ]

        self.ids_set = set(ids)

        for i, item_id in enumerate(ids):
            # Row size
            if i % ITEMS_PER_ROW == 0:
                row_frames.append(tk.Frame(self.images_frame))

            item_frame = tk.Frame(row_frames[-1])
            item_frame.grid(row=0, column=i % ITEMS_PER_ROW)

            text_frame = tk.Frame(item_frame)

            thumbnail = get_thumbnail(item_id)
            photo_image = ImageTk.PhotoImage(image=thumbnail)

            selected = self.id_data[item_id]["selected"]
            batch_toggled = self.id_data[item_id]["batch_toggled"]

            multi_batch_button = tk.Button(
                text_frame,
                text="○",
                width=2,
                fg="#FF0000" if batch_toggled else "#000000",
            )
            multi_batch_button.config(command=partial(self.select_batch, item_id))
            multi_batch_button.config(font=("Arial", 10))

            check_button = tk.Button(
                text_frame,
                text="✓" if selected else "✗",
                width=2,
                fg="#FF0000" if selected else "#000000",
            )
            check_button.config(command=partial(self.select_item, item_id))
            check_button.config(font=("Arial", 10))

            self.id_data[item_id]["buttons"] = {
                "check": check_button,
                "batch": multi_batch_button,
            }

            label = tk.Label(text_frame, text=item_id, width=10, relief="groove")
            label.config(font=("Arial", 10))

            image_label = tk.Label(item_frame, image=photo_image, width=200)
            image_label.photo = photo_image

            check_button.grid(row=0, column=0)
            label.grid(row=0, column=1)
            multi_batch_button.grid(row=0, column=2)

            image_label.grid(row=0, column=0)
            text_frame.grid(row=1, column=0)

        for i, rf in enumerate(row_frames):
            rf.grid(row=i, column=0)

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
                self.chosen_tags.pop((old_name, old_value))
            self.chosen_tags[(new_name, new_value)] = new_style

            self.reset()

    def delete_tag(self, old_name, old_value):
        if old_name == "" and old_value == "":
            return

        self.chosen_tags.pop((old_name, old_value))

        self.reset()

    def select_item(self, item_id, event=None):
        selected = self.id_data[item_id]["selected"]

        if selected:
            self.selected_ids.remove(item_id)
            self.id_data[item_id]["selected"] = False

        else:
            self.selected_ids.add(item_id)
            self.id_data[item_id]["selected"] = True

        if item_id in self.ids_set:
            select_button = self.id_data[item_id]["buttons"]["check"]
            selected = self.id_data[item_id]["selected"]
            select_button.config(
                fg="#FF0000" if selected else "#000000", text="✓" if selected else "✗"
            )

    def select_batch(self, item_id, event=None):
        self.id_data[item_id]["batch_toggled"] = not self.id_data[item_id][
            "batch_toggled"
        ]

        # Finding any IDs with batch set as true which is not ID and selecting all in batch

        batch_diffs = []
        in_batch = []
        open_batch = False

        for iter_item_id in self.ids:
            batch_toggled = self.id_data[iter_item_id]["batch_toggled"]

            if batch_toggled:
                batch_diffs.append(iter_item_id)

        if len(batch_diffs) >= 2:
            for item_id in self.ids:
                if item_id == batch_diffs[0]:
                    open_batch = True

                if open_batch:
                    in_batch.append(item_id)

                if item_id == batch_diffs[1]:
                    open_batch = False

            for item_id in in_batch:
                self.id_data[item_id]["batch_toggled"] = False
                self.id_data[item_id]["selected"] = True

                if item_id in self.ids_set:
                    self.id_data[item_id]["buttons"]["check"].config(
                        fg="#FF0000"
                        if self.id_data[item_id]["selected"]
                        else "#000000",
                        text="✓" if self.id_data[item_id]["selected"] else "✗",
                    )
                    self.id_data[item_id]["buttons"]["batch"].config(
                        fg="#FF0000"
                        if self.id_data[item_id]["batch_toggled"]
                        else "#000000"
                    )

                self.selected_ids.add(item_id)

        elif item_id in self.ids_set:
            self.id_data[item_id]["buttons"]["batch"].config(
                fg="#FF0000" if self.id_data[item_id]["batch_toggled"] else "#000000",
            )

    def reset(self):
        for widget in self.images_canvas.winfo_children():
            widget.destroy()

        self.win.quit()

    def select_all(self, event=None):
        for image_id in self.ids:
            self.id_data[image_id]["selected"] = True
            self.id_data[image_id]["batch_toggled"] = False

            if image_id in self.ids_set:
                check_button = self.id_data[image_id]["buttons"]["check"]
                batch_button = self.id_data[image_id]["buttons"]["batch"]

                check_button.config(
                    fg="#FF0000" if self.id_data[image_id]["selected"] else "#000000",
                    text="✓" if self.id_data[image_id]["selected"] else "✗",
                )
                batch_button.config(
                    fg="#FF0000"
                    if self.id_data[image_id]["batch_toggled"]
                    else "#000000"
                )

            self.selected_ids.add(image_id)

    def deselect_all(self, event=None):
        for image_id in self.ids:
            self.id_data[image_id]["selected"] = False
            self.id_data[image_id]["batch_toggled"] = False

            if image_id in self.ids_set:
                check_button = self.id_data[image_id]["buttons"]["check"]
                batch_button = self.id_data[image_id]["buttons"]["batch"]

                check_button.config(
                    fg="#FF0000" if self.id_data[image_id]["selected"] else "#000000",
                    text="✓" if self.id_data[image_id]["selected"] else "✗",
                )
                batch_button.config(
                    fg="#FF0000"
                    if self.id_data[image_id]["batch_toggled"]
                    else "#000000"
                )

            if image_id in self.selected_ids:
                self.selected_ids.remove(image_id)

    def _on_mousewheel(self, event):
        self.images_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def edit_tagname(self, entry, event=None):
        new_name = entry.get().strip().lower()
        if new_name != "":
            self.tag_name = new_name
            self.reset()

    def add_tags(self, entry, event=None):
        new_value = entry.get().strip().lower()
        if new_value == "":
            return

        add_tags(
            {item_id: {self.tag_name: [new_value]} for item_id in self.selected_ids}
        )

        for item_id in self.selected_ids:
            self.id_data.pop(item_id)

        self.selected_ids = set()
        entry.delete(0, tk.END)

        self.reset()

    def increment_page(self, event=None):
        self.page = min(self.page + 1, self.max_page - 1)
        self.load_images()

    def decrement_page(self, event=None):
        self.page = max(0, self.page - 1)
        self.load_images()

    def update_page(self, entry, event=None):
        value = entry.get().strip()
        if value == "":
            return
        if value.isdigit():
            value = int(value) - 1
            self.page = min(value, self.max_page - 1)
            self.page = max(0, self.page)
            entry.delete(0, tk.END)
            self.load_images()

    def update_items_per_page(self, entry, event=None):
        value = entry.get().strip()
        if value == "":
            return
        if value.isdigit():
            value = int(value)
            if value <= 0:
                return

            self.items_per_page = value
            self.reset()


def start_multitag_application(tag_names=[]):
    if not tag_names:
        app = MultitagApp()
        return not app.window_closed_manually, not app.tag_names

    else:
        app = MultitagApp(tag_names)
        # Second argument is whether it completed or not
        return not app.window_closed_manually, not app.tag_names


if __name__ == "__main__":
    start_multitag_application()
