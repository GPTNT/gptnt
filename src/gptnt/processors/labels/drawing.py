import cv2
import numpy as np
import structlog
from cv2.typing import MatLike

from gptnt.processors.labels.color import compute_perceived_brightness
from gptnt.processors.labels.position import get_background_corner_coords
from gptnt.processors.labels.types import Coordinates, RGBArray

log = structlog.get_logger()

FONT_SIZE = 0.7
FONT_THICKNESS = 2
BIG_BUTTON_OFFSET = 20


def draw_background(
    img: MatLike,
    coords: Coordinates,
    color: tuple[int, int, int],
    padding: int = 5,
    text_width: int = 0,
    text_height: int = 0,
    baseline: int = 0,
) -> MatLike:
    """Draw box for label for selectable component."""
    # Get size of the text
    top_left, bottom_right = get_background_corner_coords(
        coords, padding=padding, text_width=text_width, text_height=text_height, baseline=baseline
    )

    # Choose background color based on brightness
    brightness = compute_perceived_brightness(rgb=color)
    epsilon = 1e-6
    bg_color = (0, 0, 0) if brightness > (0.5 + epsilon) else (255, 255, 255)

    # Draw background rectangle
    return cv2.rectangle(img, top_left, bottom_right, bg_color, thickness=cv2.FILLED)


def draw_label(
    img: MatLike,
    label: str,
    coords: Coordinates,
    font: int,
    font_scale: float,
    color: tuple[int, int, int],
    thickness: int,
    text_width: int = 0,
    text_height: int = 0,
) -> MatLike:
    """Draw label for selectable component."""
    # Draw background rectangle
    # Calculate position to put the text so it's centered
    text_x = coords[1] - text_width // 2
    text_y = coords[0] + text_height // 2

    # Draw text
    img = cv2.putText(img, label, (text_x, text_y), font, font_scale, color, thickness)

    return img


def draw_annotation(
    img: MatLike,
    label: str,
    coords: Coordinates,
    font: int,
    font_scale: float,
    color: tuple[int, int, int],
    thickness: int,
    padding: int = 5,
) -> RGBArray:
    """Draw label for selectable component, and draw box behind it."""
    text_size, baseline = cv2.getTextSize(label, font, font_scale, thickness)
    text_width, text_height = text_size
    baseline += 1  # make sure we account for the bottom part of some letters
    img = draw_background(
        img,
        coords,
        color,
        padding=padding,
        text_width=text_width,
        text_height=text_height,
        baseline=baseline,
    )

    img = draw_label(
        img,
        label,
        coords,
        font,
        font_scale,
        color,
        thickness,
        text_width=text_width,
        text_height=text_height,
    )

    # transform img back into ndarray
    img = np.asarray(img, dtype=np.uint8)

    return img
