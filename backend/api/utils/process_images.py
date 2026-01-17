from PIL import Image
from ultralytics import YOLO
import numpy as np

MEDIA_HEIGHT = 800
FLOOR_DIVISION = 16  # Used for border thresholding

bounding_box_model = YOLO("yolov8n.pt", verbose=False)


def clamp(value, lower, upper):
    return min(max(value, lower), upper)


def get_crop_image_and_bounds(path, crop_max_height, include_bounds=True):
    base_image = Image.open(path)

    if base_image.height >= base_image.width:
        width = int(round(base_image.width * crop_max_height / base_image.height))
        height = crop_max_height
    else:
        height = int(round(base_image.height * crop_max_height / base_image.width))
        width = crop_max_height

    image = base_image.resize((width, height))

    if include_bounds:
        bounds = get_bounds(image)
        return image, bounds
    else:
        return image


def get_bounds(image):
    bounds = bounding_box_model(image, verbose=False)

    person_bounds = []
    other_bounds = []

    for bound in bounds[
        0
    ]:  # model takes batch, as we only care about 1 we use the [0] idx
        for j in range(len(bound.boxes)):
            x1, y1, x2, y2 = bound.boxes.xyxy[j].tolist()

            image_class = int(bound.boxes.cls[j])

            x1, x2, y1, y2 = clean_corners(image, (x1, x2, y1, y2))

            if image_class == 0:
                person_bounds.append((x1, x2, y1, y2))
            else:
                other_bounds.append((x1, x2, y1, y2))
    
    return person_bounds + other_bounds


def clean_corners(image, corners):  # (x1, x2, y1, y2)
    x1, x2, y1, y2 = corners

    x1, x2 = sorted([x1, x2])
    y1, y2 = sorted([y1, y2])

    # Rounding the corners
    x1, x2, y1, y2 = map(int, list((x1 - 5, x2 + 5, y1 - 5, y2 + 5)))

    x1, x2 = clamp(x1, 0, image.width), clamp(x2, 0, image.width)
    y1, y2 = clamp(y1, 0, image.height), clamp(y2, 0, image.height)

    # Move inwards where all co-ordinates are the same colour
    # o1, o2 refer to the unused axes bounds

    def get_smoothed(color):
        # Grayscale handling
        if isinstance(color, int):
            color = (color,)

        color = list(c // FLOOR_DIVISION for c in color)
        return color

    def move(start, stop, o1, o2, data_type="x"):
        delta = 1 if start <= stop else -1

        for d in range(start, stop, delta):
            cords = (d, (o1 + o2) // 2) if data_type == "x" else ((o1 + o2) // 2, d)

            color = get_smoothed(image.getpixel(cords))

            current_matches = 0
            max_matches = o2 - o1 + 1

            for o in range(o1, o2):
                cords = (d, o) if data_type == "x" else (o, d)
                checked_color = get_smoothed(image.getpixel(cords))

                if color == checked_color:
                    current_matches += 1

            if current_matches <= max_matches // 2:
                return d

        return stop

    x1 = move(x1, x2, y1, y2, data_type="x")
    x2 = move(x2 - 1, x1 - 1, y1, y2, data_type="x")
    y1 = move(y1, y2, x1, x2, data_type="y")
    y2 = move(y2 - 1, y1 - 1, x1, x2, data_type="y")

    def process_pair(p1, p2, max_value):
        # Tightening bounds
        p1, p2 = p1 + 2, p2 - 2

        # Fixing possible min-max errors
        p1, p2 = sorted([p1, p2])

        # Fixing equality errors (interval is [min, max) )
        if p1 == p2:
            p1 = max(p1 - 1, 0)
            p2 = min(p2 + 1, max_value)

        return clamp(p1, 0, max_value), clamp(p2, 0, max_value)

    x1, x2 = process_pair(x1, x2, image.width)
    y1, y2 = process_pair(y1, y2, image.height)

    return x1, x2, y1, y2


def crop_and_resize_image(base_image, corners):  # (x1, x2, y1, y2)
    x1, x2, y1, y2 = corners

    def order(a, b, max_value):
        a, b = clamp(a, 0, max_value), clamp(b, 0, max_value)
        return map(int, sorted([a, b]))

    x1, x2 = order(x1, x2, base_image.width)
    y1, y2 = order(y1, y2, base_image.height)

    cropped_image = base_image.crop((x1, y1, x2, y2))

    new_width = int(round(cropped_image.width * MEDIA_HEIGHT / cropped_image.height))
    new_height = MEDIA_HEIGHT

    resized_image = cropped_image.resize((new_width, new_height))
    return resized_image


def build_curve_from_slider(a: float):
    a = clamp(a, -1.0, 1.0)

    # Map to x on [0, 255]
    t = (a + 1.0) / 2.0
    x = t * 255.0
    y = 255.0 - x

    # Control points
    if x <= 0.0 or x >= 255.0:
        points = [
            (0.0, 0.0),
            (255.0, 255.0),
        ]
    else:
        points = [
            (0.0, 0.0),
            (x, y),
            (255.0, 255.0),
        ]

    # Interpolate across 0..255
    xs, ys = zip(*sorted(points))
    lut = np.interp(np.arange(256), xs, ys)
    lut = np.clip(lut, 0, 255).astype(np.uint8)

    return lut.tolist()


def apply_rgb_curves(img: Image.Image, a: float) -> Image.Image:
    # Takes a value frrom -1 to 1 and applies RGB curving, increasing/decreasing the brightness

    if a == 0.0:
        return img

    lut = build_curve_from_slider(a)

    r, g, b = img.convert("RGB").split()

    r = r.point(lut)
    g = g.point(lut)
    b = b.point(lut)

    return Image.merge("RGB", (r, g, b))


def rotate_image_90(img: Image.Image, turns: int = 1) -> Image.Image:
    turns = turns % 4
    if turns == 0:
        return img
    if turns == 1:
        return img.transpose(Image.ROTATE_270)
    if turns == 2:
        return img.transpose(Image.ROTATE_180)
    return img.transpose(Image.ROTATE_90)
