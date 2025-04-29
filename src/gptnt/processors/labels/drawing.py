from dataclasses import dataclass

import cv2
import numpy as np
import structlog
from cv2.typing import MatLike

from gptnt.processors.labels.color import find_text_color
from gptnt.processors.labels.position import get_background_corner_coords
from gptnt.processors.labels.types import Color, Coordinates, NumberBoxDimensions, RGBArray

log = structlog.get_logger()


@dataclass
class AnnotationBackgroundParams:
    """Parameters for drawing the background of the annotation."""

    padding: int
    alpha: float = 1


@dataclass(frozen=True)
class AnnotationTextParams:
    """Parameters for drawing the text of the annotation."""

    font_scale: float
    thickness: int
    space_between_boxes: int
    font: int = cv2.FONT_HERSHEY_SIMPLEX


def _draw_background(
    img: MatLike,
    coords: Coordinates,
    color: Color,
    text_width: int,
    text_height: int,
    drawing_params: AnnotationBackgroundParams,
) -> MatLike:
    """Draw box for label for selectable component."""
    # Get size of the text
    top_left, bottom_right = get_background_corner_coords(
        coords, padding=drawing_params.padding, text_width=text_width, text_height=text_height
    )

    if drawing_params.alpha >= 1.0:  # noqa: WPS459
        return cv2.rectangle(
            img=img, pt1=top_left, pt2=bottom_right, color=color, thickness=cv2.FILLED
        )

    overlay = img.copy()

    # draw background rectangle on overlay
    _ = cv2.rectangle(
        img=overlay, pt1=top_left, pt2=bottom_right, color=color, thickness=cv2.FILLED
    )

    # blend overlay with original image
    return cv2.addWeighted(overlay, drawing_params.alpha, img, 1 - drawing_params.alpha, 0)


def _draw_label(
    img: MatLike,
    label: str,
    coords: Coordinates,
    color: Color,
    text_width: int,
    text_height: int,
    drawing_params: AnnotationTextParams,
) -> MatLike:
    """Draw label for selectable component."""
    # Draw background rectangle
    # Calculate position to put the text so it's centered
    text_x = coords.x_pos - text_width // 2
    text_y = coords.y_pos + text_height // 2

    # determine colour of text based on brightness

    text_color = find_text_color(color)

    # Draw text
    img = cv2.putText(
        img,
        label,
        (text_x, text_y),
        drawing_params.font,
        drawing_params.font_scale,
        text_color,
        drawing_params.thickness,
    )

    return img


def draw_annotation(
    *,
    img: MatLike,
    label: str,
    color: Color,
    centroid_coords: Coordinates,
    text_drawing_params: AnnotationTextParams,
    background_drawing_params: AnnotationBackgroundParams,
) -> RGBArray:
    """Draw label for selectable component, and draw box behind it."""
    text_size, _ = cv2.getTextSize(
        label,
        text_drawing_params.font,
        text_drawing_params.font_scale,
        text_drawing_params.thickness,
    )
    text_width, text_height = text_size
    img = _draw_background(
        img,
        centroid_coords,
        color=color,
        text_width=text_width,
        text_height=text_height,
        drawing_params=background_drawing_params,
    )

    img = _draw_label(
        img,
        label,
        centroid_coords,
        color=color,
        text_width=text_width,
        text_height=text_height,
        drawing_params=text_drawing_params,
    )

    # transform img back into ndarray
    img = np.asarray(img, dtype=np.uint8)

    return img


def is_overlapping(c1: Coordinates, c2: Coordinates, dims: NumberBoxDimensions) -> bool:
    """Check if two boxes overlap given their Coordinates and dimensions."""
    return not (
        c1.x_pos + dims.width + dims.space_between <= c2.x_pos
        or c2.x_pos + dims.width + dims.space_between <= c1.x_pos
        or c1.y_pos + dims.height + dims.space_between <= c2.y_pos
        or c2.y_pos + dims.height + dims.space_between <= c1.y_pos
    )
