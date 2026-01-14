from api.views_extension import (
    get_random_compare_item,
    get_comparison_items,
    get_thumbnail,
    delete_items,
)
from api.models import Item, FileType
import tkinter as tk
from PIL import ImageTk, Image
from tkvideo import tkvideo
from functools import partial
from time import sleep
import os
import random

MAX_HEIGHT_IN_CROP = 500
SCREEN_WIDTH = 1525


def start_file(item_id):
    os.startfile(Item.objects.get(id=item_id).getpath())


class CompareApp:
    def __init__(self):
        self.win = tk.Tk()
        self.win.state("zoomed")

        self.win_exists = True
        self.win.protocol("WM_DELETE_WINDOW", self.close_window)

        self.win.geometry(f"{SCREEN_WIDTH}x1000+0+0")
        self.win.grid_rowconfigure(0, weight=1)
        self.win.grid_columnconfigure(0, weight=1)

        self.item_frame = tk.Frame(master=self.win, height=MAX_HEIGHT_IN_CROP)
        self.item_frame.grid(row=0, column=0)

        self.next_button = tk.Button(
            master=self.win,
            text="Next",
            command=self.next,
            width=120,
            font=("Arial", 16),
            height=2,
        )
        self.next_button.grid(row=1, column=0)

        self.win.bind("<Return>", self.next)

        self.change_item = False

        # (item_id, VideoPlayer)
        self.clear_video_players_set = set()

        self.video_players = {}

        while True:
            if not self.win_exists:
                break

            self.item = get_random_compare_item()

            self.comparison_item_ids = get_comparison_items(self.item.id, 30)

            self.change_item = False

            while not self.change_item:
                if not self.win_exists:
                    break

                self.load_items()

                self.win.mainloop()

        if self.win_exists:
            self.close_window()

    def clear_video_players(self):
        for item_id, player in list(self.clear_video_players_set):
            if player.item_removed:
                # Finally release to memory / GC
                self.clear_video_players_set.remove((item_id, player))

    def close_window(self):
        for widget in self.item_frame.winfo_children():
            widget.destroy()

        self.win.quit()
        self.win.destroy()

        self.win_exists = False

    def get_widget(self, item_id, frame, remaining_width, max_videos):
        # Clearing video player if exists prior
        if item_id in self.video_players:
            self.video_players.pop(item_id)

        item = Item.objects.filter(id=item_id).get()

        max_width = int(round(item.width * MAX_HEIGHT_IN_CROP / item.height))
        min_width = min(300, max_width)

        if min_width <= remaining_width:  # we can place something
            new_width = min(max_width, remaining_width)
            new_height = int(item.height * new_width / item.width)

            if item.filetype == int(FileType.Image):
                image = Image.open(item.getpath())
                resized_image = image.resize((new_width, new_height))

                photo_image = ImageTk.PhotoImage(resized_image)

                button = tk.Button(
                    master=frame,
                    image=photo_image,
                    width=new_width,
                    command=partial(start_file, item_id),
                    relief=tk.FLAT,
                    borderwidth=0,
                    highlightthickness=0,
                    padx=0,
                    pady=0,
                )
                button.image = photo_image

                label = button

            elif item.filetype == int(FileType.Video):
                if max_videos == 0:
                    image = get_thumbnail(item.id, new_width, new_height)
                    resized_image = image.resize((new_width, new_height))

                    photo_image = ImageTk.PhotoImage(resized_image)

                    label = tk.Label(
                        master=frame,
                        image=photo_image,
                        width=new_width,
                        borderwidth=0,
                        highlightthickness=0,
                        padx=0,
                        pady=0,
                    )
                    label.photo = photo_image

                else:
                    sleep(0.1)

                    label = tk.Label(
                        master=frame,
                        width=new_width,
                        borderwidth=0,
                        highlightthickness=0,
                        padx=0,
                        pady=0,
                    )

                    player = tkvideo(
                        item.getpath(), label, loop=1, size=(new_width, new_height)
                    )
                    player.play()

                    max_videos -= 1

                    self.video_players[item_id] = player

            return label, remaining_width - new_width, max_videos

        else:
            return None, remaining_width, max_videos

    def load_items(self):
        def place(item_id, position, remaining_width, max_videos=1):
            old_width = remaining_width

            frame = tk.Frame(master=self.item_frame)

            widget, remaining_width, max_videos = self.get_widget(
                item_id, frame, remaining_width, max_videos
            )

            width = old_width - remaining_width

            if widget:
                frame.grid(row=0, column=position)
                widget.grid(row=0, column=0)

                button_width = max(1, int(width / 10))

                remove_button = tk.Button(
                    master=frame,
                    text=f"{item_id} ❌",
                    command=partial(self.remove_item, item_id),
                    width=button_width,
                    fg="blue" if item_id == self.item.id else "black",
                )
                remove_button.grid(row=1, column=0)

            return remaining_width, width, max_videos

        # place first item
        remaining_width = SCREEN_WIDTH
        middle = 50
        size_on_left = 0
        size_on_right = 0
        places_on_left = 1
        places_on_right = 1

        max_videos = 0

        remaining_width, _, max_videos = place(
            self.item.id, middle, remaining_width, max_videos
        )

        for item_id in self.comparison_item_ids:
            choose_right = 1

            if size_on_right == size_on_left:
                choose_right = random.randint(0, 1)
            elif size_on_right > size_on_left:
                choose_right = 0

            if choose_right:
                remaining_width, size, max_videos = place(
                    item_id, middle + places_on_right, remaining_width, max_videos
                )
                size_on_right += size
                places_on_right += 1
            else:
                remaining_width, size, max_videos = place(
                    item_id, middle - places_on_left, remaining_width, max_videos
                )
                size_on_left += size
                places_on_left += 1

    def remove_item(self, item_id):
        if item_id == self.item.id:
            self.change_item = True

        if item_id in self.video_players:
            player = self.video_players[item_id]
            player.stop()
            player.toggle_fn = partial(delete_items, {item_id})

            self.video_players.pop(item_id)

            # Queueing to clean up
            self.clear_video_players_set.add((item_id, player))

        else:
            delete_items({item_id})

        self.comparison_item_ids = [
            iid for iid in self.comparison_item_ids if iid != item_id
        ]
        self.reset()

    def next(self, event=None):
        self.change_item = True
        self.reset()

    def reset(self):
        for widget in self.item_frame.winfo_children():
            widget.destroy()

        self.win.quit()


def start_compare_application():
    CompareApp()


if __name__ == "__main__":
    start_compare_application()
