import io
from typing import NamedTuple, overload

import cv2
import numpy as np
from numpy.typing import NDArray
from PIL import Image
from skimage.measure import regionprops

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


class Bbox(NamedTuple):
    """Structure of a bounding box of a region."""

    min_row: int
    min_col: int
    max_row: int
    max_col: int


class RegionProperties(NamedTuple):
    """Specify the structure of a region's properties."""

    label: int
    centroid: Coordinate
    bbox: Bbox


def convert_colorful_segm_to_labeled(image_as_array: RGBArray) -> NDArray[np.int8]:
    """Convert colourful segmentation to a labelled image.

    Input shape: (height, width, channels = 3)
    Output shape: (height, width)
    """
    # flatten image and group colour channels together
    height, width, color_chan = image_as_array.shape
    # shape: (height * width, channels = 3)
    flattened = image_as_array.reshape(-1, color_chan)
    # find unique colours and assign labels
    _, inverse = np.unique(flattened, axis=0, return_inverse=True)

    # reshape the labels to image dimensions again
    # shape: (height, width)
    return inverse.reshape(height, width).astype(np.int8)


def get_region_properties(labeled_image: NDArray[np.int8]) -> list[RegionProperties]:
    """Extract region properties from a labelled image."""
    props = regionprops(labeled_image)

    return [
        RegionProperties(
            label=region.label,
            centroid=Coordinate(round(region.centroid[1]), round(region.centroid[0])),
            bbox=Bbox(*region.bbox),
        )
        for region in props
    ]


def draw_bounding_box_on_image(
    *, image: RGBArray, bbox: Bbox, color: Color, thickness: int
) -> RGBArray:
    """Draw bounding box based off of bbos region property."""
    _ = cv2.rectangle(
        image,
        (bbox.min_col, bbox.min_row),
        (bbox.max_col, bbox.max_row),
        color=color,
        thickness=thickness,
    )
    return image


def draw_label_on_image(  # noqa: WPS210
    *,
    image: RGBArray,
    text: str,
    position: Coordinate,
    box_color: Color,
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
    text_box_left = position.x_pos - text_width // 2
    text_box_top = position.y_pos - text_height // 2
    text_box_right = position.x_pos + text_width // 2
    text_box_bottom = position.y_pos + text_height // 2

    _ = cv2.rectangle(
        image,
        (text_box_left - padding, text_box_top - padding),
        (text_box_right + padding, text_box_bottom + padding),
        color=box_color,
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


def draw_region_labels(
    *,
    image: RGBArray,
    regions: list[RegionProperties],
    box_color: Color,
    text_color: Color,
    font_scale: float,
    box_thickness: int,
    text_thickness: int,
    padding: int,
    add_labels: bool,
    add_bbox: bool,
) -> RGBArray:
    """Place label numbers on image based on region properties."""
    annotated_image = image.copy()

    for region in regions:
        if add_bbox:
            _ = draw_bounding_box_on_image(
                image=annotated_image, bbox=region.bbox, color=box_color, thickness=box_thickness
            )

        if add_labels:
            _ = draw_label_on_image(
                image=annotated_image,
                text=str(region.label),
                position=region.centroid,
                box_color=box_color,
                text_color=text_color,
                font_scale=font_scale,
                thickness=text_thickness,
                padding=padding,
            )

    return annotated_image


class SetOfMarksHandler:
    """Create a handler that manages the SoM labelling on screenshots of ktane."""

    def __init__(
        self,
        *,
        box_color: Color = GREEN,
        text_color: Color = BLACK,
        font_scale: float = 0.5,
        box_thickness: int = 2,
        text_thickness: int = 1,
        padding: int = 1,
        add_labels: bool = True,
        add_bbox: bool = True,
    ) -> None:
        self._box_color = box_color
        self._text_color = text_color
        self._font_scale = font_scale
        self._box_thickness = box_thickness
        self._text_thickness = text_thickness
        self._padding = padding
        self._add_labels = add_labels
        self._add_bbox = add_bbox

    @overload
    def run(self, *, observation: RGBArray, colorful_image: RGBArray) -> RGBArray: ...

    @overload
    def run(self, *, observation: bytes, colorful_image: bytes) -> bytes: ...

    def run(
        self, *, observation: RGBArray | bytes, colorful_image: RGBArray | bytes
    ) -> RGBArray | bytes:
        """Convert screenshot + seg mask to annotated screenshot in bytes or RBGArray form."""
        if isinstance(observation, np.ndarray) and isinstance(colorful_image, np.ndarray):
            return self.run_from_array(observation=observation, colorful_image=colorful_image)

        if isinstance(observation, bytes) and isinstance(colorful_image, bytes):
            return self.run_from_bytes(observation=observation, colorful_image=colorful_image)

        raise TypeError(
            "Both observation and colorful_image must be either RGBArray or bytes. "
            "Mixing types is not allowed."
        )

    def run_from_array(self, *, observation: RGBArray, colorful_image: RGBArray) -> RGBArray:
        """Handle the labelling and bounding box drawing on the screenshot based on segmentation.

        Output: Annotated screenshot with bounding boxes and labels drawn.
        """
        labeled_segmentation = convert_colorful_segm_to_labeled(colorful_image)
        regions = get_region_properties(labeled_segmentation)

        annotated_screenshot = draw_region_labels(
            image=observation,
            regions=regions,
            box_color=self._box_color,
            text_color=self._text_color,
            font_scale=self._font_scale,
            box_thickness=self._box_thickness,
            text_thickness=self._text_thickness,
            padding=self._padding,
            add_labels=self._add_labels,
            add_bbox=self._add_bbox,
        )
        if annotated_screenshot.shape[2] == ALPHA_CHANNEL:
            annotated_screenshot = annotated_screenshot[:, :, :3]

        return annotated_screenshot

    def run_from_bytes(self, *, observation: bytes, colorful_image: bytes) -> bytes:  # noqa: WPS210
        """Convert bytes to RGBArrays, run annotation, then convert back to bytes."""
        obs_image = Image.open(io.BytesIO(initial_bytes=observation)).convert("RGB")
        obs_array = np.array(obs_image, dtype=np.uint8)

        col_image = Image.open(io.BytesIO(initial_bytes=colorful_image)).convert("RGB")
        col_array = np.array(col_image, dtype=np.uint8)

        annotated_array = self.run_from_array(observation=obs_array, colorful_image=col_array)

        # save to bytes buffer
        buffer = io.BytesIO()
        Image.fromarray(annotated_array).save(buffer, format="PNG")
        return buffer.getvalue()
