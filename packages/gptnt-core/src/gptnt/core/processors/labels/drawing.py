from dataclasses import dataclass

import cv2
import numpy as np
import structlog
from cv2.typing import MatLike
from numpy.typing import NDArray

from gptnt.core.processors.labels.color import find_text_color
from gptnt.core.processors.labels.position import get_background_corner_coords
from gptnt.core.processors.labels.types import (  # noqa: WPS235
    BLACK,
    WHITE,
    Color,
    Coordinates,
    NumberBoxDimensions,
    RGBArray,
)

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
            img=img,
            pt1=top_left,
            pt2=bottom_right,
            color=color,
            thickness=cv2.FILLED,
            lineType=cv2.LINE_AA,
        )

    overlay = img.copy()

    # draw background rectangle on overlay
    _ = cv2.rectangle(
        img=overlay,
        pt1=top_left,
        pt2=bottom_right,
        color=color,
        thickness=cv2.FILLED,
        lineType=cv2.LINE_AA,
    )

    # blend overlay with original image
    return cv2.addWeighted(overlay, drawing_params.alpha, img, 1 - drawing_params.alpha, 0)


def _draw_background_triangle(
    img: MatLike,
    coords: Coordinates,
    color1: Color,  # color for first triangle (top-left to bottom-right diagonal)
    color2: Color,  # color for second triangle (bottom-left to top-right diagonal)
    text_width: int,
    text_height: int,
    drawing_params: AnnotationBackgroundParams,
) -> MatLike:
    """Draw two triangles for label background instead of a rectangle."""
    top_left, bottom_right = get_background_corner_coords(
        coords, padding=drawing_params.padding, text_width=text_width, text_height=text_height
    )

    x1, y1 = top_left
    x2, y2 = bottom_right

    pts_triangle1 = np.array([[x1, y1], [x2, y1], [x2, y2]], dtype=np.int32)  # top-right triangle
    pts_triangle2 = np.array(
        [[x1, y1], [x1, y2], [x2, y2]], dtype=np.int32
    )  # bottom-left triangle

    if drawing_params.alpha >= 1.0:  # noqa: WPS459
        _ = cv2.fillPoly(img, [pts_triangle1], color1, lineType=cv2.LINE_AA)
        _ = cv2.fillPoly(img, [pts_triangle2], color2, lineType=cv2.LINE_AA)
        return img

    overlay = img.copy()

    _ = cv2.fillPoly(overlay, [pts_triangle1], color1, lineType=cv2.LINE_AA)
    _ = cv2.fillPoly(overlay, [pts_triangle2], color2, lineType=cv2.LINE_AA)

    return cv2.addWeighted(overlay, drawing_params.alpha, img, 1 - drawing_params.alpha, 0)


def _draw_label(
    img: MatLike,
    label: str,
    coords: Coordinates,
    color: tuple[Color, ...],
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

    if len(color) == 1:
        text_color = find_text_color(color[0])
    elif WHITE in color:
        text_color = BLACK
    else:
        text_color = WHITE

    # Draw text
    img = cv2.putText(
        img,
        label,
        (text_x, text_y),
        drawing_params.font,
        drawing_params.font_scale,
        text_color,
        drawing_params.thickness,
        lineType=cv2.LINE_AA,
    )

    return img


def draw_annotation(
    *,
    img: MatLike,
    label: str,
    color: tuple[Color, ...],
    centroid_coords: Coordinates,
    text_drawing_params: AnnotationTextParams,
    background_drawing_params: AnnotationBackgroundParams,
) -> RGBArray:
    """Draw label for selectable component, and draw box behind it."""
    if len(color) == 0:
        log.warning("No color provided for label, skipping drawing.")
        img = np.asarray(img, dtype=np.uint8)
        return img

    if len(color) > 1:
        text_size, _ = cv2.getTextSize(
            label,
            text_drawing_params.font,
            text_drawing_params.font_scale,
            text_drawing_params.thickness,
        )
        text_width, text_height = text_size
        img = _draw_background_triangle(
            img,
            centroid_coords,
            color1=color[0],
            color2=color[1],
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
    else:
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
            color=color[0],
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


def draw_mask_on_image(  # noqa: WPS210
    *,
    image: RGBArray,
    coords: NDArray[np.intp],
    color: tuple[Color, ...],
    thickness: int,
    soft_mask_alpha: float,
) -> tuple[RGBArray, NDArray[np.bool_]]:
    """Draw outline of a single region with optional color split for top/bottom."""
    # blank mask
    mask = np.zeros_like(image[:, :, 0])

    # get all region pixels on the mask
    mask[coords[:, 0], coords[:, 1]] = 255

    # dilate mask to expand it outward
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    dilated_mask = cv2.dilate(mask, kernel, iterations=2)

    # find external contours
    contours, _ = cv2.findContours(dilated_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if soft_mask_alpha > 0:
        soft_mask_color = color[0]  # fallback if multiple
        soft_mask = np.zeros_like(image)
        _ = cv2.drawContours(soft_mask, contours, -1, soft_mask_color, cv2.FILLED)

        mask_region = cv2.drawContours(
            np.zeros_like(mask), contours, -1, WHITE, cv2.FILLED, lineType=cv2.LINE_AA
        )
        mask_region = mask_region.astype(bool)

        image[mask_region] = (
            image[mask_region] * (1 - soft_mask_alpha) + soft_mask[mask_region] * soft_mask_alpha
        ).astype(np.uint8)

    if len(color) == 1:
        # standard single-color outline
        _ = cv2.drawContours(
            image=image,
            contours=contours,
            contourIdx=-1,
            color=color[0],
            thickness=thickness,
            lineType=cv2.LINE_AA,
        )
    else:
        # split top/bottom logic
        contour_mask = np.zeros_like(image[:, :, 0])
        _ = cv2.drawContours(
            contour_mask, contours, -1, WHITE, thickness=thickness, lineType=cv2.LINE_AA
        )

        rows = np.any(mask, axis=1)
        nonzero_row_indices = np.where(rows)[0]

        if nonzero_row_indices.size > 0:
            height = nonzero_row_indices[-1] - nonzero_row_indices[0] + 1
        else:
            height = 0  # no masked area

        midpoint = height // 2
        quarter_height = midpoint // 2

        mask_start = nonzero_row_indices[0]
        mask_end = nonzero_row_indices[-1]

        top_mask = np.zeros_like(contour_mask)
        top_mask[mask_start : mask_start + quarter_height, :] = 1

        middle_top_mask = np.zeros_like(contour_mask)
        middle_top_mask[mask_start + quarter_height : mask_start + midpoint, :] = 1

        middle_bottom_mask = np.zeros_like(contour_mask)
        middle_bottom_mask[mask_start + midpoint : mask_start + midpoint + quarter_height, :] = 1

        bottom_mask = np.zeros_like(contour_mask)
        bottom_mask[mask_start + midpoint + quarter_height : mask_end, :] = 1

        color_top, color_bottom = color[:2]

        top_contour = cv2.bitwise_and(contour_mask, contour_mask, mask=top_mask)
        image[top_contour > 0] = color_top

        middle_top_contour = cv2.bitwise_and(contour_mask, contour_mask, mask=middle_top_mask)
        image[middle_top_contour > 0] = color_bottom

        middle_bottom_contour = cv2.bitwise_and(
            contour_mask, contour_mask, mask=middle_bottom_mask
        )
        image[middle_bottom_contour > 0] = color_top

        bottom_contour = cv2.bitwise_and(contour_mask, contour_mask, mask=bottom_mask)
        image[bottom_contour > 0] = color_bottom

    return image, dilated_mask.astype(bool)
