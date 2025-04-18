import colorsys
from typing import NamedTuple

import cv2
import numpy as np
from numpy.typing import NDArray
from skimage.color import hsv2rgb, rgb2hsv
from skimage.measure import regionprops
from skimage.measure._regionprops import RegionProperties

type Color = tuple[int, int, int]
type RGBArray = NDArray[np.uint8]

BLACK: Color = (0, 0, 0)
WHITE: Color = (255, 255, 255)
GREEN: Color = (0, 255, 0)
ALPHA_CHANNEL = 4


class Coordinate(NamedTuple):
    """Structure of a centroid of a region."""

    x_pos: int
    y_pos: int


def hue_to_rgb(hue: float) -> Color:
    """Convert hue value to rgb."""
    red_val, green_val, blue_val = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
    return (int(red_val * 255), int(green_val * 255), int(blue_val * 255))  # noqa: WPS432


def blend_with_image(image: RGBArray, mask: RGBArray, alpha: float = 0.3) -> RGBArray:
    """Blend a mask with an image using alpha transparency."""
    blended = cv2.addWeighted(mask, alpha, image, 1 - alpha, 0)
    return np.asarray(blended, dtype=np.uint8)


def convert_colorful_segm_to_labeled(image_as_array: RGBArray) -> NDArray[np.int8]:  # noqa: WPS210
    """Convert colourful segmentation to a labelled image.

    Input shape: (height, width, channels = 3)
    Output shape: (height, width)
    """
    # flatten image and group colour channels together
    height, width, color_chan = image_as_array.shape
    # shape: (height * width, channels = 3)
    flattened = image_as_array.reshape(-1, color_chan)

    # make the brightness of all non-black colours equal to 1 (mitigates the anti-aliasing of seg mask)
    non_black_color_mask = flattened.sum(axis=-1) > 0
    flattened_hsv = rgb2hsv(flattened)
    flattened_hsv[:, 2] = non_black_color_mask
    floating_rgb = hsv2rgb(flattened_hsv) * 255  # noqa: WPS432
    fixed_rgb = floating_rgb.astype(np.uint8)

    # find unique colours and assign labels
    _, inverse = np.unique(fixed_rgb, axis=0, return_inverse=True)

    # reshape the labels to image dimensions again
    # shape: (height, width)
    return inverse.reshape(height, width).astype(np.int8)


def get_region_properties(labeled_image: NDArray[np.int8]) -> list[RegionProperties]:
    """Extract region properties from a labelled image."""
    props = regionprops(labeled_image)

    return props


def convert_to_grayscale(image: RGBArray) -> RGBArray:
    """Convert an image to grayscale while maintaining 3 channels."""
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    grayscale = cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)
    return np.asarray(grayscale, dtype=np.uint8)


def draw_mask_on_image(  # noqa: WPS210
    *,
    image: RGBArray,
    coords: NDArray[np.intp],
    color: Color,
    thickness: int,
    soft_mask_alpha: float,
) -> tuple[RGBArray, NDArray[np.bool_]]:
    """Draw outline of a single region based on its coordinates."""
    # blank mask
    mask = np.zeros_like(image[:, :, 0])

    # get all region pixels on the mask
    for y_coord, x_coord in coords:
        mask[y_coord, x_coord] = 255

    # dilate mask to expand it outward
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    dilated_mask = cv2.dilate(mask, kernel, iterations=2)

    # draw contours on image
    contours, _ = cv2.findContours(dilated_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if soft_mask_alpha > 0:
        soft_mask = np.zeros_like(image)
        _ = cv2.drawContours(soft_mask, contours, -1, color, cv2.FILLED)

        # alpha blend soft mask over image
        mask_region = cv2.drawContours(np.zeros_like(mask), contours, -1, WHITE, cv2.FILLED)
        mask_region = mask_region.astype(bool)

        # blend only in masked area
        image[mask_region] = (
            image[mask_region] * (1 - soft_mask_alpha) + soft_mask[mask_region] * soft_mask_alpha
        ).astype(np.uint8)

    _ = cv2.drawContours(
        image=image, contours=contours, contourIdx=-1, color=color, thickness=thickness
    )

    return image, dilated_mask.astype(bool)


def draw_label_on_image(  # noqa: WPS210
    *,
    image: RGBArray,
    text: str,
    position: Coordinate,
    mask_color: Color,
    text_color: Color,
    font_scale: float,
    thickness: int,
    padding: int,
) -> RGBArray:
    """Draw a number label on an image."""
    (text_width, text_height), _ = cv2.getTextSize(
        text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness
    )

    # background rectangle
    text_box_left = int(position.x_pos - text_width // 2)
    text_box_top = int(position.y_pos - text_height // 2)
    text_box_right = int(position.x_pos + text_width // 2)
    text_box_bottom = int(position.y_pos + text_height // 2)

    _ = cv2.rectangle(
        img=image,
        pt1=(text_box_left - padding, text_box_top - padding),
        pt2=(text_box_right + padding, text_box_bottom + padding),
        color=mask_color,
        thickness=cv2.FILLED,
    )

    # label text
    _ = cv2.putText(
        image,
        text,
        (text_box_left, text_box_bottom),
        fontFace=cv2.FONT_HERSHEY_SIMPLEX,
        fontScale=font_scale,
        color=text_color,
        thickness=thickness,
        lineType=cv2.LINE_AA,
    )

    return image


def draw_region_labels(  # noqa: WPS210, WPS211
    *,
    image: RGBArray,
    regions: list[RegionProperties],
    text_color: Color,
    font_scale: float,
    mask_thickness: int,
    text_thickness: int,
    padding: int,
    add_labels: bool,
    add_mask_outline: bool,
    soft_mask_alpha: float,
    bw_outside_mask: bool,
) -> RGBArray:
    """Place label numbers on image based on region properties."""
    annotated_image = image.copy()

    # initialise combined mask
    height, width = image.shape[:2]
    combined_mask = (
        np.zeros((height, width), dtype=bool) if bw_outside_mask and add_mask_outline else None
    )

    for idx, region in enumerate(regions):
        # convert HSV to RGB
        hue = idx / len(regions)  # evenly spaced between 0 and 1
        mask_color: Color = hue_to_rgb(hue)

        if add_mask_outline:
            _, mask = draw_mask_on_image(
                image=annotated_image,
                coords=region.coords,
                color=mask_color,
                thickness=mask_thickness,
                soft_mask_alpha=soft_mask_alpha,
            )

            # add the masks together with bitwise OR
            if combined_mask is not None:
                combined_mask |= mask

        if add_labels:
            _ = draw_label_on_image(
                image=annotated_image,
                text=str(region.label),
                position=Coordinate(*region.centroid[::-1]),
                mask_color=mask_color,
                text_color=text_color,
                font_scale=font_scale,
                thickness=text_thickness,
                padding=padding,
            )

    # convert areas outside all masks to grayscale
    if combined_mask is not None:
        gray_image = convert_to_grayscale(annotated_image)
        annotated_image[~combined_mask] = gray_image[~combined_mask]

    return annotated_image


class SetOfMarksHandler:
    """Create a handler that manages the SoM labelling on screenshots of ktane."""

    def __init__(
        self,
        *,
        text_color: Color = BLACK,
        font_scale: float = 0.5,
        mask_thickness: int = 2,
        text_thickness: int = 1,
        padding: int = 1,
        add_labels: bool = True,
        add_mask_outline: bool = True,
        soft_mask_alpha: float = 0.15,
        bw_outside_mask: bool = True,
    ) -> None:
        self._text_color = text_color
        self._font_scale = font_scale
        self._mask_thickness = mask_thickness
        self._text_thickness = text_thickness
        self._padding = padding
        self._add_labels = add_labels
        self._add_mask_outline = add_mask_outline
        self._soft_mask_alpha = soft_mask_alpha
        self._bw_outside_mask = bw_outside_mask

    def run(self, *, observation: RGBArray, colorful_image: RGBArray) -> RGBArray:
        """Handle the labelling and bounding box drawing on the screenshot based on segmentation.

        Output: Annotated screenshot with bounding boxes and labels drawn.
        """
        labeled_segmentation = convert_colorful_segm_to_labeled(colorful_image)
        regions = get_region_properties(labeled_segmentation)

        annotated_screenshot = draw_region_labels(
            image=observation,
            regions=regions,
            text_color=self._text_color,
            font_scale=self._font_scale,
            mask_thickness=self._mask_thickness,
            text_thickness=self._text_thickness,
            padding=self._padding,
            add_labels=self._add_labels,
            add_mask_outline=self._add_mask_outline,
            soft_mask_alpha=self._soft_mask_alpha,
            bw_outside_mask=self._bw_outside_mask,
        )
        if annotated_screenshot.shape[2] == ALPHA_CHANNEL:
            annotated_screenshot = annotated_screenshot[:, :, :3]

        return annotated_screenshot
