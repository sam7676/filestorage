from api.views_extension import (
    get_next_clip_item,
    get_nearest_item,
    get_thumbnail,
    edit_item,
    delete_items,
    start_file,
)
import tkinter as tk
from PIL import ImageTk
from tkvideo import tkvideo
from api.models import Item, FileType, FileState
from PIL import Image
from functools import partial

MAX_HEIGHT_IN_CROP = 650
MAX_WIDTH_OF_CROP = 700
SCREEN_WIDTH = 1920
THUMBNAIL_MODE = True


class ClipApplication:
    def __init__(self):
        self.win = tk.Tk()
        self.win.state("zoomed")

        self.win_exists = True
        self.win.protocol("WM_DELETE_WINDOW", self.close_window)

        self.win.geometry(f"{SCREEN_WIDTH}x1000+0+0")
        self.win.grid_rowconfigure(0, weight=1)
        self.win.grid_columnconfigure(0, weight=1)

        self.main_frame = tk.Frame(master=self.win, height=MAX_HEIGHT_IN_CROP)
        self.main_frame.grid(row=0, column=0)

        self.win.bind("<Return>", self.choose_middle)

        self.ids = [-1]

        last_item_id = None
        last_nearest_item_id = None
        self.swap = False

        while self.ids:
            if not self.win_exists:
                break

            item_id = get_next_clip_item()

            if item_id is not None:
                item = Item.objects.get(id=item_id)
                nearest_item_id = get_nearest_item(item_id, item.label, item.filetype)

                self.ids = [item_id]

                self.item_id = item_id
                self.nearest_item_id = nearest_item_id

                # No other items in our label
                if self.nearest_item_id == -1:
                    self.approve(self.item_id)

                else:
                    if (
                        last_item_id != item_id
                        and last_nearest_item_id != nearest_item_id
                    ):
                        self.swap = False

                    last_item_id = item_id
                    last_nearest_item_id = nearest_item_id

                    self.load_items()

                    self.win.mainloop()

            else:
                self.ids = []

        if self.win_exists:
            self.close_window()

    def close_window(self):
        self.win.quit()
        self.win.destroy()

        self.win_exists = False

    def reset(self):
        for widget in self.main_frame.winfo_children():
            widget.destroy()

        self.win.quit()

    def get_widget(self, frame, item_id):
        item = Item.objects.filter(id=item_id).get()

        new_width = int(round(item.width * MAX_HEIGHT_IN_CROP / item.height))
        new_height = MAX_HEIGHT_IN_CROP

        if new_width > MAX_WIDTH_OF_CROP:
            new_width = MAX_WIDTH_OF_CROP
            new_height = int(round(new_width * item.height / item.width))

        if THUMBNAIL_MODE:
            resized_image = get_thumbnail(item.id, new_width, new_height)

            photo_image = ImageTk.PhotoImage(resized_image)

            if item.filetype == int(FileType.Image):
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

            else:
                label = tk.Label(master=frame, image=photo_image, width=new_width)
                label.photo = photo_image

            return label

        else:
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
                label = tk.Label(master=frame, width=new_width)

                player = tkvideo(
                    item.getpath(), label, loop=1, size=(new_width, new_height)
                )
                player.play()

                return label

    def load_items(self):
        item_frame = tk.Frame(master=self.main_frame)
        button_frame = tk.Frame(master=self.main_frame)

        item_frame.grid(row=0, column=0)
        button_frame.grid(row=1, column=0)

        self.left_item_frame = tk.Frame(master=item_frame)
        self.right_item_frame = tk.Frame(master=item_frame)

        item_type = Item.objects.get(id=self.item_id).filetype
        nearest_item_type = Item.objects.get(id=self.nearest_item_id).filetype

        self.left_item_id = self.item_id if not self.swap else self.nearest_item_id
        self.right_item_id = self.nearest_item_id if not self.swap else self.item_id

        left_item_type = item_type if not self.swap else nearest_item_type
        right_item_type = nearest_item_type if not self.swap else item_type

        type_to_str_map = {0: "image", 1: "video"}

        self.left_item_frame.grid(row=0, column=0)
        self.right_item_frame.grid(row=0, column=1)

        left_item_label = self.get_widget(self.left_item_frame, self.left_item_id)
        left_item_label.grid(row=0, column=0, sticky="n")

        right_item_label = self.get_widget(self.right_item_frame, self.right_item_id)
        right_item_label.grid(row=0, column=0, sticky="n")

        left_label_frame = tk.Frame(master=self.left_item_frame)
        left_label_frame.grid(row=1, column=0, sticky="s")

        left_id_label = tk.Label(
            master=left_label_frame, text=f"{self.left_item_id}", width=7
        )
        left_id_label.grid(row=0, column=0)

        left_type_label = tk.Label(
            master=left_label_frame,
            text=f"{type_to_str_map[left_item_type]}",
            width=5,
            bg="#FFFFFF" if left_item_type == 0 else "#FFAAAA",
        )
        left_type_label.grid(row=0, column=1)

        right_label_frame = tk.Frame(master=self.right_item_frame)
        right_label_frame.grid(row=1, column=0, sticky="s")

        right_id_label = tk.Label(
            master=right_label_frame, text=f"{self.right_item_id}", width=7
        )
        right_id_label.grid(row=0, column=0)

        right_type_label = tk.Label(
            master=right_label_frame,
            text=f"{type_to_str_map[right_item_type]}",
            width=5,
            bg="#FFFFFF" if right_item_type == 0 else "#FFAAAA",
        )
        right_type_label.grid(row=0, column=1)

        actual_button_frame = tk.Frame(master=button_frame)
        actual_button_frame.grid(row=1, column=0)

        keep_left_button = tk.Button(
            master=actual_button_frame, text="Left", width=8, command=self.choose_left
        )
        keep_both_button = tk.Button(
            master=actual_button_frame, text="Both", width=8, command=self.choose_middle
        )
        keep_right_button = tk.Button(
            master=actual_button_frame, text="Right", width=8, command=self.choose_right
        )

        keep_left_button.grid(row=0, column=0)
        keep_both_button.grid(row=0, column=1)
        keep_right_button.grid(row=0, column=2)

        keepnone_swap_frame = tk.Frame(master=button_frame)
        keepnone_swap_frame.grid(row=2, column=0, pady=(5, 0))

        keep_none_button = tk.Button(
            master=keepnone_swap_frame, text="None", width=13, command=self.choose_none
        )
        keep_none_button.grid(row=0, column=0)

        swap_button = tk.Button(
            master=keepnone_swap_frame,
            text="Swap",
            width=13,
            fg="#FF0000" if self.swap else "#000000",
            command=self.change_swap,
        )
        swap_button.grid(row=0, column=1)

    def approve(self, item_id):
        edit_item(item_id=item_id, new_state=int(FileState.NeedsTags))
        self.reset()

    def delete(self, item_id):
        delete_items((item_id,))
        self.reset()

    def choose_left(self):
        self.delete(self.right_item_id)

    def choose_middle(self, event=None):
        self.approve(self.item_id)

    def choose_right(self):
        self.delete(self.left_item_id)

    def choose_none(self):
        self.delete(self.left_item_id)
        self.delete(self.right_item_id)

    def change_swap(self, event=None):
        self.swap = not self.swap
        self.reset()


def start_clip_application():
    ClipApplication()
