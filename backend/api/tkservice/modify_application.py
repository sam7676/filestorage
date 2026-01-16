from api.views_extension import (
    get_top_x_needsmodify_ids,
    get_thumbnail,
    edit_item,
    delete_items,
    start_file
)
from api.utils.process_images import crop_and_resize_image
from api.models import Item, FileState
import tkinter as tk
from PIL import ImageTk, Image
from functools import partial
from threading import Thread
import os

ITEMS_ON_PAGE = 4


class ModifyApp:
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
        # }

        self.scrollbar_y = None
        self.images_canvas = None
        self.main_frame = tk.Frame()

        self.scrollbar_y_pos = (0.0, 0.0)

        self.ids = [-1]

        while self.ids:
            if not self.win_exists:
                break

            self.ids = get_top_x_needsmodify_ids(100)

            if not self.ids:
                break

            # Collecting PhotoImages
            for item_id in self.ids:
                if item_id in self.id_data:
                    continue

                thumbnail = get_thumbnail(item_id)

                self.id_data[item_id] = {
                    "photo_image": ImageTk.PhotoImage(image=thumbnail),
                }

            self.load()
            Thread(target=self.move_scrollbar).start()
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

    def move_scrollbar(self):
        self.images_canvas.yview_moveto(self.scrollbar_y_pos[0])
        self.scrollbar_y.set(self.scrollbar_y_pos[0], self.scrollbar_y_pos[1])

    def load(self):
        self.main_frame = tk.Frame()
        self.main_frame.grid(row=0, column=0)

        self.main_frame.grid_rowconfigure(0, weight=1)
        self.main_frame.grid_columnconfigure(0, weight=1)

        sub_frame = tk.Frame(self.main_frame)
        sub_frame.grid(row=0, column=0)

        refresh_button = tk.Button(
            self.main_frame, text="Refresh", command=self.refresh_reset
        )
        refresh_button.grid(row=1, column=0)

        # Canvas

        canvas = tk.Canvas(sub_frame, width=200 * (ITEMS_ON_PAGE + 0.5), height=700)
        self.scrollbar_y = tk.Scrollbar(
            sub_frame, orient="vertical", command=canvas.yview
        )

        self.image_frame_parent = sub_frame

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

    def load_images(self):
        # Clear existing widgets
        for widget in self.images_frame.winfo_children():
            widget.destroy()

        row_frames = []
        ids_per_row = []

        for i, item_id in enumerate(self.ids):
            # Row size
            if i % ITEMS_ON_PAGE == 0:
                row_frames.append(tk.Frame(self.images_frame))
                ids_per_row.append([])

            item_frame = tk.Frame(row_frames[-1])
            item_frame.grid(row=0, column=i % ITEMS_ON_PAGE)

            text_frame = tk.Frame(item_frame)

            photo_image = self.id_data[item_id]["photo_image"]

            move_button = tk.Button(
                text_frame, text="M", width=2, command=partial(self.move_item, item_id)
            )

            label = tk.Button(
                text_frame,
                text=item_id,
                width=10,
                relief="groove",
                command=partial(start_file, item_id),
            )
            label.config(font=("Arial", 10))

            delete_button = tk.Button(
                text_frame,
                text="X",
                width=2,
                command=partial(self.delete_item, item_id),
            )

            image_label = tk.Label(item_frame, image=photo_image, width=200)
            image_label.photo = photo_image

            move_button.grid(row=0, column=0)
            label.grid(row=0, column=1)
            delete_button.grid(row=0, column=2)

            image_label.grid(row=0, column=0)
            text_frame.grid(row=1, column=0)

            ids_per_row[-1].append(item_id)

        for i, rf in enumerate(row_frames):
            rf.grid(row=i, column=0)

            open_row_button = tk.Button(
                master=self.images_frame,
                text="Open row",
                height=10,
                command=partial(self.open_items, ids_per_row[i]),
            )
            open_row_button.grid(row=i, column=1)

    def reset(self):
        for widget in self.images_canvas.winfo_children():
            widget.destroy()

        if self.scrollbar_y:
            self.scrollbar_y_pos = self.scrollbar_y.get()

        self.win.quit()

    def refresh_reset(self):
        self.id_data = {}
        self.reset()

    def move_item(self, item_id):
        path = Item.objects.get(id=item_id).getpath()

        image = Image.open(path)

        image = crop_and_resize_image(
            image, (0, image.width, 0, image.height)
        )
        image.save(path)

        new_width = image.width
        new_height = image.height
        image.close()

        edit_item(
            item_id=item_id,
            new_state=int(FileState.NeedsLabel),
            new_width=new_width,
            new_height=new_height,
        )
        self.reset()

    def open_items(self, item_ids):
        for item_id in item_ids:
            os.startfile(Item.objects.filter(id=item_id).get().getpath())

    def delete_item(self, item_id):
        delete_items({item_id})
        self.reset()

    def _on_mousewheel(self, event):
        self.images_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")


def start_modify_application():
    app = ModifyApp()
    return not app.window_closed_manually, True


if __name__ == "__main__":
    start_modify_application()
