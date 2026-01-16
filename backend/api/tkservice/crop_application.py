from api.views_extension import (
    get_next_crop_item,
    crop_and_resize_from_view,
    delete_items,
)
from api.utils.process_images import apply_rgb_curves
from api.models import FileState
import tkinter as tk
from PIL import ImageTk
from math import ceil


SCALE_CONSTANT = 2
FLOOR_DIVISION = 16
MAX_HEIGHT_IN_CROP = 700


class CropApp:
    def __init__(self):
        self.win = tk.Tk()
        self.win.state("zoomed")

        self.win_exists = True
        self.win.protocol("WM_DELETE_WINDOW", self.close_window_manual)
        self.window_closed_manually = False

        self.win.geometry("1920x1000+0+0")
        self.win.grid_rowconfigure(0, weight=1)
        self.win.grid_columnconfigure(0, weight=1)

        self.scale = SCALE_CONSTANT
        self.scale_ind = 1
        self.bounds_ind = 0

        # Canvas, displays the images to crop

        self.canvas_frame = tk.Frame()
        self.canvas_frame.grid(row=0, column=0)

        # Buttons: delete, confirm, modify, duplicate

        button_frame = tk.Frame()
        button_frame.grid(row=1, column=0)

        delete_button = tk.Button(
            master=button_frame, text="Delete", command=self.delete
        )
        delete_button.grid(row=0, column=0)

        confirm_button = tk.Button(
            master=button_frame, text="Enter", command=self.confirm
        )
        confirm_button.grid(row=0, column=1)

        self.scale_label = tk.Button(
            master=button_frame, text=f"Scale: {self.scale_ind}"
        )
        self.scale_label.grid(row=0, column=2)

        self.bounds_label = tk.Button(
            master=button_frame,
            text=f"Bounds: {self.bounds_ind} / 0",
            command=self.reset_bounds,
        )
        self.bounds_label.grid(row=0, column=3)

        modify_button = tk.Button(
            master=button_frame, text="Modify", command=self.modify
        )
        modify_button.grid(row=0, column=4)

        modify_copy_button = tk.Button(
            master=button_frame, text="Modify Copy", command=self.modify_copy
        )
        modify_copy_button.grid(row=0, column=5)

        duplicate_button = tk.Button(
            master=button_frame, text="Copy", command=self.copy
        )
        duplicate_button.grid(row=0, column=6)

        # Bindings

        self.win.bind("<Return>", self.confirm)
        self.win.bind("c", self.copy)
        self.win.bind("<Delete>", self.delete)
        self.win.bind("m", self.modify)
        self.win.bind("n", self.modify_copy)

        self.win.bind("w", lambda _: self.move_up(1))
        self.win.bind("a", lambda _: self.move_left(1))
        self.win.bind("s", lambda _: self.move_down(1))
        self.win.bind("d", lambda _: self.move_right(1))

        self.win.bind("r", self.reset_bounds)

        self.win.bind("<Up>", lambda _: self.move_up(2))
        self.win.bind("<Left>", lambda _: self.move_left(2))
        self.win.bind("<Down>", lambda _: self.move_down(2))
        self.win.bind("<Right>", lambda _: self.move_right(2))

        self.win.bind("[", self.decrease_scale)
        self.win.bind("]", self.increase_scale)

        self.win.bind("<Prior>", self.decrease_bounds)
        self.win.bind("<Next>", self.increase_bounds)

        self.left_canvas_cords = None
        self.right_canvas_cords = None

        data = 1

        while data is not None:
            if not self.win_exists:
                break

            data = get_next_crop_item(MAX_HEIGHT_IN_CROP)

            if data is not None:
                image, bounds, item_id = data

                self.image = image

                self.bounds = bounds
                self.item_id = item_id

                self.alpha = 0.0

                self.load_image()

        if self.win_exists:
            self.close_window()

    def close_window(self):
        for widget in self.canvas_frame.winfo_children():
            widget.destroy()

        self.win.quit()
        self.win.destroy()

        self.win_exists = False

    def close_window_manual(self):
        self.window_closed_manually = True
        self.close_window()

    def load_image(self):
        # Getting settings

        self.scale = SCALE_CONSTANT
        self.scale_ind = 1
        self.scale_label.configure(text=f"Scale: {self.scale_ind}")

        self.canvas_frame = tk.Frame()
        self.canvas_frame.grid(row=0, column=0)

        imageTk = ImageTk.PhotoImage(self.image)

        # Building canvas and assigning events

        self.canvas = tk.Canvas(
            master=self.canvas_frame, width=self.image.width, height=self.image.height
        )
        self.canvas.grid(row=0, column=0)

        self.canvas.create_image(0, 0, image=imageTk, anchor="nw")
        self.canvas.bind("<Button-1>", self.left_click_canvas)
        self.canvas.bind("<Button-3>", self.right_click_canvas)

        self.canvas.bind("<Return>", self.confirm)
        self.canvas.bind("c", self.copy)
        self.canvas.bind("<Delete>", self.delete)
        self.canvas.bind("m", self.modify)
        self.canvas.bind("n", self.modify_copy)

        self.canvas.bind("w", lambda _: self.move_up(1))
        self.canvas.bind("a", lambda _: self.move_left(1))
        self.canvas.bind("s", lambda _: self.move_down(1))
        self.canvas.bind("d", lambda _: self.move_right(1))

        self.canvas.bind("r", self.reset_bounds)

        self.canvas.bind("<Up>", lambda _: self.move_up(2))
        self.canvas.bind("<Left>", lambda _: self.move_left(2))
        self.canvas.bind("<Down>", lambda _: self.move_down(2))
        self.canvas.bind("<Right>", lambda _: self.move_right(2))

        self.canvas.bind("[", self.decrease_scale)
        self.canvas.bind("]", self.increase_scale)

        self.canvas.bind("<Prior>", self.decrease_bounds)
        self.canvas.bind("<Next>", self.increase_bounds)

        self.canvas.grid(row=0, column=0)

        self.preview_image_label = tk.Label(master=self.canvas_frame, image=imageTk)
        self.preview_image_label.grid(row=0, column=1, sticky="W")

        self.slider = tk.Scale(
            master=self.canvas_frame,
            from_=-1,
            to=1,
            orient=tk.VERTICAL,
            resolution=0.01,
            length=400,
        )

        self.slider.grid(row=0, column=2, sticky="W")
        self.slider.bind("<ButtonRelease-1>", self.on_slider_release)

        # Canvas variables (for drawing on canvas)

        self.left_canvas_cords = None
        self.right_canvas_cords = None
        self.identifiers = []

        # Handling bounds

        self.bounds_ind = 0
        self.bounds_label.configure(
            text=f"Bounds: {min(self.bounds_ind + 1, len(self.bounds))} / {len(self.bounds)}"
        )

        if self.bounds:
            x1, x2, y1, y2 = self.bounds[self.bounds_ind]

            self.left_canvas_cords = [x1, y1]
            self.right_canvas_cords = [x2, y2]

        self.make_rectangle_canvas()

        self.win.mainloop()

    def left_click_canvas(self, event):
        x, y = event.x, event.y
        self.left_canvas_cords = (x, y)
        self.make_rectangle_canvas()

    def right_click_canvas(self, event):
        x, y = event.x, event.y
        self.right_canvas_cords = (x, y)
        self.make_rectangle_canvas()

    def reset_bounds(self, event=None):
        self.left_canvas_cords = (0, 0)
        self.right_canvas_cords = (self.image.width, self.image.height)
        self.make_rectangle_canvas()

    def make_rectangle_canvas(self):
        # Clear previous rectangles
        for identifier in self.identifiers:
            self.canvas.delete(identifier)

        # Update coordinates to ensure max
        if self.left_canvas_cords and self.right_canvas_cords:
            if self.left_canvas_cords[0] == self.right_canvas_cords[0]:
                self.left_canvas_cords[0] = max(self.left_canvas_cords[0] - 1, 0)
                self.right_canvas_cords[0] = min(
                    self.right_canvas_cords[0] + 1, self.image.width
                )

            if self.left_canvas_cords[1] == self.right_canvas_cords[1]:
                self.left_canvas_cords[1] = max(self.left_canvas_cords[1] - 1, 0)
                self.right_canvas_cords[1] = min(
                    self.right_canvas_cords[1] + 1, self.image.height
                )

            x1 = min(self.left_canvas_cords[0], self.right_canvas_cords[0])
            y1 = min(self.left_canvas_cords[1], self.right_canvas_cords[1])

            x2 = max(self.left_canvas_cords[0], self.right_canvas_cords[0])
            y2 = max(self.left_canvas_cords[1], self.right_canvas_cords[1])

            self.left_canvas_cords = (x1, y1)
            self.right_canvas_cords = (x2, y2)

            # Draw rectangle between the two clicks
            self.identifiers.append(
                self.canvas.create_rectangle(
                    x1, y1, x2, y2, fill="", outline="red", width=1
                )
            )

        if self.left_canvas_cords:
            # Draw small rectangle around left click
            left_change = (
                self.left_canvas_cords[0] - 3,
                self.left_canvas_cords[1] - 3,
                self.left_canvas_cords[0] + 3,
                self.left_canvas_cords[1] + 3,
            )

            self.identifiers.append(
                self.canvas.create_rectangle(
                    left_change, fill="green", width=2, outline="green"
                )
            )

        if self.right_canvas_cords:
            # Draw small rectangle around right click
            right_change = (
                self.right_canvas_cords[0] - 3,
                self.right_canvas_cords[1] - 3,
                self.right_canvas_cords[0] + 3,
                self.right_canvas_cords[1] + 3,
            )

            self.identifiers.append(
                self.canvas.create_rectangle(
                    right_change, fill="blue", width=2, outline="blue"
                )
            )

        if self.left_canvas_cords and self.right_canvas_cords:
            self.preview_image_label.destroy()
            del self.preview_image_label

            preview = self.image.crop(
                (
                    self.left_canvas_cords[0],
                    self.left_canvas_cords[1],
                    self.right_canvas_cords[0],
                    self.right_canvas_cords[1],
                )
            )
            preview = apply_rgb_curves(preview, self.alpha)

            preview_proposed_width = int(
                round(preview.width * self.image.height / preview.height)
            )

            preview_given_height = self.image.height

            if preview_proposed_width < preview_given_height:
                preview = preview.resize((preview_proposed_width, preview_given_height))

            preview_image = ImageTk.PhotoImage(preview)

            self.preview_image_label = tk.Label(
                master=self.canvas_frame, image=preview_image
            )
            self.preview_image_label.photo = preview_image

            self.preview_image_label.grid(row=0, column=1)

    def confirm(self, event=None):
        if self.left_canvas_cords and self.right_canvas_cords:
            x1, y1 = self.left_canvas_cords
            x2, y2 = self.right_canvas_cords

            if x1 is not None and x2 is not None and y1 is not None and y2 is not None:
                crop_and_resize_from_view(
                    item_id=self.item_id,
                    rendered_size=(self.image.width, self.image.height),
                    crop=(x1, x2, y1, y2),
                    new_state=FileState.NeedsLabel,
                    save_or_new="save",
                    alpha=self.alpha,
                )

            else:
                crop_and_resize_from_view(
                    item_id=self.item_id,
                    rendered_size=(self.image.width, self.image.height),
                    crop=(None, None, None, None),
                    new_state=FileState.NeedsLabel,
                    save_or_new="save",
                    alpha=self.alpha,
                )
        else:
            crop_and_resize_from_view(
                item_id=self.item_id,
                rendered_size=(self.image.width, self.image.height),
                crop=(None, None, None, None),
                new_state=FileState.NeedsLabel,
                save_or_new="save",
                alpha=self.alpha,
            )

        self.reset()

    def copy(self, event=None):
        if self.left_canvas_cords and self.right_canvas_cords:
            x1, y1 = self.left_canvas_cords
            x2, y2 = self.right_canvas_cords

            if x1 is not None and x2 is not None and y1 is not None and y2 is not None:
                crop_and_resize_from_view(
                    item_id=self.item_id,
                    rendered_size=(self.image.width, self.image.height),
                    crop=(x1, x2, y1, y2),
                    new_state=FileState.NeedsLabel,
                    save_or_new="new",
                    alpha=self.alpha,
                )

            else:
                crop_and_resize_from_view(
                    item_id=self.item_id,
                    rendered_size=(self.image.width, self.image.height),
                    crop=(None, None, None, None),
                    new_state=FileState.NeedsLabel,
                    save_or_new="new",
                    alpha=self.alpha,
                )
        else:
            crop_and_resize_from_view(
                item_id=self.item_id,
                rendered_size=(self.image.width, self.image.height),
                crop=(None, None, None, None),
                new_state=FileState.NeedsLabel,
                save_or_new="new",
                alpha=self.alpha,
            )

        self.reset()

    def modify(self, event=None):
        if self.left_canvas_cords and self.right_canvas_cords:
            x1, y1 = self.left_canvas_cords
            x2, y2 = self.right_canvas_cords

            if x1 is not None and x2 is not None and y1 is not None and y2 is not None:
                crop_and_resize_from_view(
                    item_id=self.item_id,
                    rendered_size=(self.image.width, self.image.height),
                    crop=(x1, x2, y1, y2),
                    new_state=FileState.NeedsModify,
                    save_or_new="save",
                    alpha=self.alpha,
                )

            else:
                crop_and_resize_from_view(
                    item_id=self.item_id,
                    rendered_size=(self.image.width, self.image.height),
                    crop=(None, None, None, None),
                    new_state=FileState.NeedsModify,
                    save_or_new="save",
                    alpha=self.alpha,
                )
        else:
            crop_and_resize_from_view(
                item_id=self.item_id,
                rendered_size=(self.image.width, self.image.height),
                crop=(None, None, None, None),
                new_state=FileState.NeedsModify,
                save_or_new="save",
                alpha=self.alpha,
            )

        self.reset()

    def modify_copy(self, event=None):
        if self.left_canvas_cords and self.right_canvas_cords:
            x1, y1 = self.left_canvas_cords
            x2, y2 = self.right_canvas_cords

            if x1 is not None and x2 is not None and y1 is not None and y2 is not None:
                crop_and_resize_from_view(
                    item_id=self.item_id,
                    rendered_size=(self.image.width, self.image.height),
                    crop=(x1, x2, y1, y2),
                    new_state=FileState.NeedsModify,
                    save_or_new="save",
                    alpha=self.alpha,
                )

            else:
                crop_and_resize_from_view(
                    item_id=self.item_id,
                    rendered_size=(self.image.width, self.image.height),
                    crop=(None, None, None, None),
                    new_state=FileState.NeedsModify,
                    save_or_new="new",
                    alpha=self.alpha,
                )
        else:
            crop_and_resize_from_view(
                item_id=self.item_id,
                rendered_size=(self.image.width, self.image.height),
                crop=(None, None, None, None),
                new_state=FileState.NeedsModify,
                save_or_new="new",
                alpha=self.alpha,
            )

        self.reset()

    def delete(self, event=None):
        delete_items(item_ids=(self.item_id,))

        self.reset()

    def move_up(self, val):
        if val == 1 and self.left_canvas_cords:
            y = self.left_canvas_cords[1]
            y = max(y - self.scale, 0)
            self.left_canvas_cords = (self.left_canvas_cords[0], y)
            self.make_rectangle_canvas()

        elif val == 2 and self.right_canvas_cords:
            y = self.right_canvas_cords[1]
            y = max(y - self.scale, 0)
            self.right_canvas_cords = (self.right_canvas_cords[0], y)
            self.make_rectangle_canvas()

    def move_down(self, val):
        if val == 1 and self.left_canvas_cords:
            y = self.left_canvas_cords[1]
            y = min(y + self.scale, MAX_HEIGHT_IN_CROP)
            self.left_canvas_cords = (self.left_canvas_cords[0], y)
            self.make_rectangle_canvas()

        elif val == 2 and self.right_canvas_cords:
            y = self.right_canvas_cords[1]
            y = min(y + self.scale, MAX_HEIGHT_IN_CROP)
            self.right_canvas_cords = (self.right_canvas_cords[0], y)
            self.make_rectangle_canvas()

    def move_left(self, val):
        if val == 1 and self.left_canvas_cords:
            x = self.left_canvas_cords[0]
            x = max(x - self.scale, 0)
            self.left_canvas_cords = (x, self.left_canvas_cords[1])
            self.make_rectangle_canvas()

        elif val == 2 and self.right_canvas_cords:
            x = self.right_canvas_cords[0]
            x = max(x - self.scale, 0)
            self.right_canvas_cords = (x, self.right_canvas_cords[1])
            self.make_rectangle_canvas()

    def move_right(self, val):
        if val == 1 and self.left_canvas_cords:
            x = self.left_canvas_cords[0]
            x = min(x + self.scale, self.image.width)
            self.left_canvas_cords = (x, self.left_canvas_cords[1])
            self.make_rectangle_canvas()

        elif val == 2 and self.right_canvas_cords:
            x = self.right_canvas_cords[0]
            x = min(x + self.scale, self.image.width)
            self.right_canvas_cords = (x, self.right_canvas_cords[1])
            self.make_rectangle_canvas()

    def decrease_scale(self, event=None):
        self.scale = ceil(self.scale / SCALE_CONSTANT)
        self.scale_ind = max(0, self.scale_ind - 1)
        self.scale_label.configure(text=f"Scale: {self.scale_ind}")

    def increase_scale(self, event=None):
        self.scale = ceil(self.scale * SCALE_CONSTANT)
        self.scale_ind += 1
        self.scale_label.configure(text=f"Scale: {self.scale_ind}")

    def increase_bounds(self, event=None):
        if self.bounds:
            self.bounds_ind = (self.bounds_ind + 1) % len(self.bounds)

            x1, x2, y1, y2 = self.bounds[self.bounds_ind]

            self.left_canvas_cords = (x1, y1)
            self.right_canvas_cords = (x2, y2)

            self.make_rectangle_canvas()

        else:
            pass

        self.bounds_label.configure(
            text=f"Bounds: {min(self.bounds_ind + 1, len(self.bounds))} / {len(self.bounds)}"
        )

    def decrease_bounds(self, event=None):
        if self.bounds:
            self.bounds_ind = (self.bounds_ind - 1) % len(self.bounds)

            x1, x2, y1, y2 = self.bounds[self.bounds_ind]

            self.left_canvas_cords = (x1, y1)
            self.right_canvas_cords = (x2, y2)

            self.make_rectangle_canvas()

        else:
            pass

        self.bounds_label.configure(
            text=f"Bounds: {min(self.bounds_ind + 1, len(self.bounds))} / {len(self.bounds)}"
        )

    def reset(self):
        for widget in self.canvas_frame.winfo_children():
            widget.destroy()

        self.win.quit()

    def on_slider_release(self, event):
        self.alpha = float(self.slider.get())
        self.make_rectangle_canvas()


def start_crop_application():
    app = CropApp()
    return not app.window_closed_manually, True


if __name__ == "__main__":
    start_crop_application()
