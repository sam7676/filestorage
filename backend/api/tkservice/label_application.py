from api.views_extension import (
    get_top_x_unlabelled_ids,
    get_all_labels,
    get_thumbnail,
    edit_item,
)
from api.models import FileState
import tkinter as tk
from PIL import ImageTk
from functools import partial

ITEMS_ON_PAGE = 6
TOTAL_ITEMS = 60


class LabelApp:
    def __init__(self):
        self.win = tk.Tk()
        self.win.state("zoomed")

        self.win_exists = True
        self.win.protocol("WM_DELETE_WINDOW", self.close_window_manual)
        self.window_closed_manually = False

        self.win.geometry("1920x1000+0+0")
        self.win.grid_rowconfigure(0, weight=1)
        self.win.grid_columnconfigure(0, weight=1)

        self.selected_ids = set()
        self.id_data = {}
        # {
        #     "photo_image": None,
        #     "selected": False,
        #     "batch_toggled": False,
        #     "buttons": {
        #         "check": None,
        #         "batch": None
        #     },
        # }

        self.scrollbar_y = None
        self.images_canvas = None
        self.main_frame = tk.Frame()

        self.scrollbar_y_pos = (0.0, 0.0)
        self.label_input = ""

        self.ids = [-1]

        while self.ids:
            if not self.win_exists:
                break

            self.ids = get_top_x_unlabelled_ids(TOTAL_ITEMS)
            self.labels = [
                item["label"] for item in get_all_labels() if item["label"] != ""
            ]
            self.labels.sort()

            if not self.ids:
                break

            # Collecting PhotoImages
            for item_id in self.ids:
                if item_id in self.id_data:
                    continue

                thumbnail = get_thumbnail(item_id)

                self.id_data[item_id] = {
                    "photo_image": ImageTk.PhotoImage(image=thumbnail),
                    "selected": False,
                    "batch_toggled": False,
                }

            self.load()
            self.win.mainloop()

        if self.win_exists:
            self.close_window()

    def close_window(self):
        for widget in self.main_frame.winfo_children():
            widget.destroy()

        self.win.quit()
        self.win.destroy()

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

        image_frame = tk.Frame(left_frame)
        image_frame.grid(row=1, column=0)

        # Canvas

        canvas = tk.Canvas(image_frame, width=150 * ITEMS_ON_PAGE, height=700)
        self.scrollbar_y = tk.Scrollbar(
            image_frame, orient="vertical", command=canvas.yview
        )

        self.image_frame_parent = image_frame

        self.images_frame = tk.Frame(canvas)
        self.images_frame.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=self.images_frame, anchor="nw")
        canvas.configure(yscrollcommand=self.scrollbar_y.set)

        # Pack scrollbars and canvas
        self.scrollbar_y.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        self.images_canvas = canvas
        self.images_canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        # Load images into canvas

        self.load_images()

        # Right frame

        enter_label = tk.Label(
            text="Enter label", master=right_frame, width=23, relief="groove"
        )
        enter_label.grid(row=2, column=0, sticky="nw")

        self.entry_var = tk.StringVar()
        self.entry_var.trace_add("write", self.on_entry_change)

        self.enter_bar = tk.Entry(
            master=right_frame, textvariable=self.entry_var, width=27
        )
        self.enter_bar.insert(0, self.label_input)
        self.enter_bar.bind("<Return>", self.on_entry_change)
        self.enter_bar.grid(row=3, column=0, sticky="nw")

        self.results_frame = tk.Frame(master=right_frame, height=500, width=200)
        self.results_frame.grid(row=4, column=0, sticky="nw")

        self.on_entry_change()

    def load_images(self):
        # Clear existing widgets
        for widget in self.images_frame.winfo_children():
            widget.destroy()

        row_frames = []

        for i, item_id in enumerate(self.ids):
            # Row size
            if i % ITEMS_ON_PAGE == 0:
                row_frames.append(tk.Frame(self.images_frame))

            item_frame = tk.Frame(row_frames[-1])
            item_frame.grid(row=0, column=i % ITEMS_ON_PAGE)

            text_frame = tk.Frame(item_frame)

            photo_image = self.id_data[item_id]["photo_image"]
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

    def select_item(self, item_id, event=None):
        selected = self.id_data[item_id]["selected"]

        if selected:
            self.selected_ids.remove(item_id)
            self.id_data[item_id]["selected"] = False

        else:
            self.selected_ids.add(item_id)
            self.id_data[item_id]["selected"] = True

        select_button = self.id_data[item_id]["buttons"]["check"]
        select_button.config(
            fg="#FF0000" if self.id_data[item_id]["selected"] else "#000000",
            text="✓" if self.id_data[item_id]["selected"] else "✗",
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

                self.id_data[item_id]["buttons"]["check"].config(
                    fg="#FF0000" if self.id_data[item_id]["selected"] else "#000000",
                    text="✓" if self.id_data[item_id]["selected"] else "✗",
                )
                self.id_data[item_id]["buttons"]["batch"].config(
                    fg="#FF0000"
                    if self.id_data[item_id]["batch_toggled"]
                    else "#000000"
                )

                self.selected_ids.add(item_id)

        else:
            self.id_data[item_id]["buttons"]["batch"].config(
                fg="#FF0000" if self.id_data[item_id]["batch_toggled"] else "#000000"
            )

    def reset(self):
        for widget in self.images_canvas.winfo_children():
            widget.destroy()

        if self.scrollbar_y:
            self.scrollbar_y_pos = self.scrollbar_y.get()

        self.win.quit()

    def select_all(self, event=None):
        for image_id in self.ids:
            self.id_data[image_id]["selected"] = True
            self.id_data[image_id]["batch_toggled"] = False

            check_button = self.id_data[image_id]["buttons"]["check"]
            batch_button = self.id_data[image_id]["buttons"]["batch"]

            check_button.config(
                fg="#FF0000" if self.id_data[image_id]["selected"] else "#000000",
                text="✓" if self.id_data[image_id]["selected"] else "✗",
            )
            batch_button.config(
                fg="#FF0000" if self.id_data[image_id]["batch_toggled"] else "#000000"
            )

            self.selected_ids.add(image_id)

    def deselect_all(self, event=None):
        for image_id in self.ids:
            self.id_data[image_id]["selected"] = False
            self.id_data[image_id]["batch_toggled"] = False

            check_button = self.id_data[image_id]["buttons"]["check"]
            batch_button = self.id_data[image_id]["buttons"]["batch"]

            check_button.config(
                fg="#FF0000" if self.id_data[image_id]["selected"] else "#000000",
                text="✓" if self.id_data[image_id]["selected"] else "✗",
            )
            batch_button.config(
                fg="#FF0000" if self.id_data[image_id]["batch_toggled"] else "#000000"
            )

            if image_id in self.selected_ids:
                self.selected_ids.remove(image_id)

    def _on_mousewheel(self, event):
        self.images_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def on_entry_change(self, *args):
        for widget in self.results_frame.winfo_children():
            widget.destroy()

        for i in range(11):
            self.results_frame.rowconfigure(i, weight=0)

        self.results_frame.grid_propagate(0)

        user_input = self.enter_bar.get().strip()
        self.label_input = user_input

        result_labels = []

        for label in self.labels:
            if label.startswith(user_input):
                result_labels.append(label)

            if len(result_labels) == 10:
                break

        i = 0
        for label in result_labels:
            tk_label = tk.Label(
                master=self.results_frame,
                text=f"{label}",
                width=20,
                relief="groove",
                height=1,
            )

            tk_label.grid(row=i, column=0, sticky="n")

            button = tk.Button(
                master=self.results_frame,
                text="+",
                command=partial(self.modify_items, label),
                width=2,
                height=1,
            )
            button.grid(row=i, column=1, sticky="n")

            i += 1

        if user_input not in result_labels and user_input != "":
            label = tk.Label(
                master=self.results_frame,
                text=f"{user_input}",
                width=20,
                relief="groove",
                height=1,
            )
            label.grid(row=i, column=0, sticky="n")

            button = tk.Button(
                master=self.results_frame,
                text="+",
                command=partial(self.modify_items, user_input),
                width=2,
                height=1,
            )
            button.grid(row=i, column=1, sticky="ns")

            i += 1

        empty_row = tk.Label(master=self.results_frame, text="", width=2, height=1)
        empty_row.grid(row=i, column=0, sticky="n")

        self.results_frame.rowconfigure(i, weight=1)

    def modify_items(self, label):
        if label == "":
            return

        for item_id in self.selected_ids:
            edit_item(
                item_id=item_id, new_label=label, new_state=int(FileState.NeedsClip)
            )

            self.id_data.pop(item_id)

        self.selected_ids = set()
        self.enter_bar.delete(0, tk.END)
        self.label_input = ""

        if label not in self.labels:
            self.labels.append(label)
        self.labels.sort()

        self.reset()


def start_label_application():
    app = LabelApp()
    return not app.window_closed_manually, True


if __name__ == "__main__":
    start_label_application()
