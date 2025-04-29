import itertools
import string
from collections.abc import Callable, Generator, Mapping
from dataclasses import dataclass
from functools import lru_cache, partial
from types import MappingProxyType
from typing import ClassVar, Literal

import cv2
import numpy as np
import structlog
from numpy.typing import NDArray
from skimage.color import hsv2rgb, rgb2hsv
from skimage.measure import regionprops

from gptnt.ktane.actions import RelativeCoordinate
from gptnt.ktane.state.modules import KtaneComponent
from gptnt.players.actions import SetOfMarksLocation
from gptnt.processors.labels.color import (
    ENTIRELY_COLOR_DEPENDENT_MODULES,
    boost_vibrancy,
    get_median_colour,
)
from gptnt.processors.labels.drawing import (
    AnnotationBackgroundParams,
    AnnotationTextParams,
    draw_annotation,
)
from gptnt.processors.labels.keypad import keypad
from gptnt.processors.labels.maze import maze
from gptnt.processors.labels.memory import memory
from gptnt.processors.labels.morse import morse_code
from gptnt.processors.labels.password import password
from gptnt.processors.labels.simon import simon
from gptnt.processors.labels.types import (  # noqa: WPS235
    BLUE,
    GREEN,
    IS_LINE_THRESHOLD,
    RED,
    WHITE,
    YELLOW,
    Color,
    Coordinates,
    DrawData,
    NumberBoxDimensions,
    RegionProperties,
    RGBArray,
)
from gptnt.processors.labels.venn import venn
from gptnt.processors.labels.whos_on_first import whos_on_first
from gptnt.processors.labels.wire_sequence import wire_sequence
from gptnt.processors.labels.wires import wires
from gptnt.processors.labels.zoomed_out import zoomed_out

_logger = structlog.get_logger()

PROPS_AREA_THRESHOLD = 10
BIG_BUTTON_OFFSET = -6

COMPONENT_WRITE_LABEL_MAPPER: Mapping[
    KtaneComponent | None,
    Callable[[list[RegionProperties], NumberBoxDimensions], Generator[DrawData]],
] = MappingProxyType(
    {
        None: zoomed_out,
        KtaneComponent.big_button: partial(zoomed_out, offset=BIG_BUTTON_OFFSET),
        KtaneComponent.memory: memory,
        KtaneComponent.morse_code: morse_code,
        KtaneComponent.password: password,
        KtaneComponent.simon: simon,
        KtaneComponent.keypad: keypad,
        KtaneComponent.whos_on_first: whos_on_first,
        KtaneComponent.maze: maze,
        KtaneComponent.wires: wires,
        KtaneComponent.venn: venn,
        KtaneComponent.wire_sequence: wire_sequence,
    }
)


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
    flattened_hsv[:, 1] = non_black_color_mask
    flattened_hsv[:, 0] = np.round(flattened_hsv[:, 0], 2)
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
    props = [props for props in props if props.area > PROPS_AREA_THRESHOLD]
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


def get_region_color(
    image: RGBArray,
    segm_image: RGBArray,
    region: RegionProperties,
    module: KtaneComponent | None,
    saturation_boost: float,
    value_boost: float,
) -> Color:
    """Get the colour of a region based on the module type."""
    # Use image colours for colour dependent modules (but only wire interactables for wire modules)
    if module in ENTIRELY_COLOR_DEPENDENT_MODULES or (
        module == KtaneComponent.wire_sequence and region.eccentricity > IS_LINE_THRESHOLD
    ):
        color = get_median_colour(region, image)
        return boost_vibrancy(color, saturation_boost=saturation_boost, value_boost=value_boost)

    if module == KtaneComponent.wire_sequence:
        # Set the colors of the wire_sequence buttons so that they do not match one of the wires
        color = get_median_colour(region, segm_image)
        if color == RED:
            return GREEN
        if color == BLUE:
            return YELLOW

    # Otherwise, use segmentation image colour
    return get_median_colour(region, segm_image)


@dataclass
class MaskDrawingParams:
    """Parameters for drawing masks on the image."""

    mask_thickness: int
    soft_mask_alpha: float
    bw_outside_mask: bool
    color_dependent_saturation_boost: float
    color_dependent_value_boost: float


def draw_region_masks(  # noqa: WPS210, WPS211
    *,
    image: RGBArray,
    segm_image: RGBArray,
    regions: list[RegionProperties],
    zoomed_in_component: KtaneComponent | None,
    drawing_params: MaskDrawingParams,
) -> RGBArray:
    """Place label numbers on image based on region properties."""
    annotated_image = image.copy()

    # initialise combined mask
    height, width = image.shape[:2]
    combined_mask = (
        np.zeros((height, width), dtype=bool) if drawing_params.bw_outside_mask else None
    )

    for region in regions:
        mask_color = get_region_color(
            image,
            segm_image,
            region,
            zoomed_in_component,
            drawing_params.color_dependent_saturation_boost,
            drawing_params.color_dependent_value_boost,
        )

        _, mask = draw_mask_on_image(
            image=annotated_image,
            coords=region.coords,
            color=mask_color,
            thickness=drawing_params.mask_thickness,
            soft_mask_alpha=drawing_params.soft_mask_alpha,
        )

        # add the masks together with bitwise OR
        if combined_mask is not None:
            combined_mask |= mask

    # convert areas outside all masks to grayscale
    if combined_mask is not None:
        gray_image = convert_to_grayscale(annotated_image)
        annotated_image[~combined_mask] = gray_image[~combined_mask]

    return annotated_image


@lru_cache(maxsize=1)
def compute_sample_text_dimensions(*, text: str, params: AnnotationTextParams) -> tuple[int, int]:
    """Compute the dimensions of a sample text using the given parameters."""
    (text_width, text_height), _ = cv2.getTextSize(
        text=text, fontFace=params.font, fontScale=params.font_scale, thickness=params.thickness
    )
    return text_width, text_height


class SetOfMarksHandler:
    """Create a handler that manages the SoM labelling on screenshots of ktane."""

    # Create a list of possible labels for set of marks if using the alphabet, up to 2-letter
    # combinations of uppercase letters.
    alphabet: ClassVar[list[str]] = list(
        itertools.chain(
            string.ascii_uppercase,
            map("".join, itertools.combinations_with_replacement(string.ascii_uppercase, 2)),
        )
    )

    def __init__(
        self,
        *,
        annotation_text_params: AnnotationTextParams,
        annotation_background_params: AnnotationBackgroundParams,
        mask_drawing_params: MaskDrawingParams,
        add_labels: bool = True,
        add_mask_outline: bool = True,
        mark_type: Literal["alphabet", "number"] = "alphabet",
    ) -> None:
        self._annotation_text_params = annotation_text_params
        self._annotation_background_params = annotation_background_params
        self._mask_drawing_params = mask_drawing_params

        self._add_labels = add_labels
        self._add_mask_outline = add_mask_outline

        self._mark_type = mark_type
        self._mark_to_coordinate: dict[SetOfMarksLocation, RelativeCoordinate] = {}

    def extract_regions(self, colorful_image: RGBArray) -> list[RegionProperties]:
        """Extract regions from a colourful segmentation image."""
        labeled_segmentation = convert_colorful_segm_to_labeled(colorful_image)
        regions = get_region_properties(labeled_segmentation)
        self._update_mark_to_coordinate_mapping(regions)
        return regions

    def run(
        self,
        *,
        observation: RGBArray,
        colorful_image: RGBArray,
        state: KtaneComponent | None = None,
    ) -> RGBArray:
        """Handle the labelling and bounding box drawing on the screenshot based on segmentation.

        Output: Annotated screenshot with bounding boxes and labels drawn.
        """
        regions = self.extract_regions(colorful_image)

        # find which bomb component is currently selected
        zoomed_in_component = state

        # convert regions to relative coordinates and store them
        annotated_image = draw_region_masks(
            image=observation,
            segm_image=colorful_image,
            regions=regions,
            zoomed_in_component=zoomed_in_component,
            drawing_params=self._mask_drawing_params,
        )

        # add numbered labels to image
        annotated_image = self.draw_labels(
            image=annotated_image,
            segm_img=colorful_image,
            regions=regions,
            module=zoomed_in_component,
        )
        return annotated_image

    def mark_to_coordinate(self, *, mark_id: SetOfMarksLocation) -> RelativeCoordinate:
        """Convert a mark ID to a relative coordinate."""
        if mark_id not in self._mark_to_coordinate:
            _logger.exception(
                "Mark ID not found in mapping", mark_id=mark_id, mapping=self._mark_to_coordinate
            )
        return self._mark_to_coordinate[mark_id]

    def draw_labels(
        self,
        *,
        image: RGBArray,
        segm_img: RGBArray,
        regions: list[RegionProperties],
        module: KtaneComponent | None,
    ) -> RGBArray:
        """Draw labels on the image based on the segmentation image and observation."""
        text_width, text_height = compute_sample_text_dimensions(
            text="A", params=self._annotation_text_params
        )

        # Get list of coordinates to draw labels
        draw_coords = COMPONENT_WRITE_LABEL_MAPPER[module](
            regions,
            NumberBoxDimensions(
                width=text_width,
                height=text_height,
                padding=self._annotation_background_params.padding,
                space_between=self._annotation_text_params.space_between_boxes,
            ),
        )

        annotated_image = image.copy()

        for draw_location, region in draw_coords:
            # Get the colour of the region
            color = get_region_color(
                image,
                segm_img,
                region,
                module,
                self._mask_drawing_params.color_dependent_saturation_boost,
                self._mask_drawing_params.color_dependent_value_boost,
            )
            # Ensure the label is an integer, which is should be but skimage is not type safe
            assert isinstance(region.label, int), (
                f"Label {region.label} is not an integer. Label type: {type(region.label)}"
            )

            annotated_image = draw_annotation(
                img=annotated_image,
                label=str(self._format_label(region.label)),
                centroid_coords=Coordinates(y_pos=draw_location[0], x_pos=draw_location[1]),
                color=color,
                text_drawing_params=self._annotation_text_params,
                background_drawing_params=self._annotation_background_params,
            )

        return annotated_image

    def _update_mark_to_coordinate_mapping(self, regions: list[RegionProperties]) -> None:
        """Map the region label to a relative coordinate."""
        label_to_coord = {
            self._format_label(region.label): RelativeCoordinate(
                x_pos=region.centroid[1] / region._label_image.shape[1],  # noqa: SLF001
                y_pos=region.centroid[0] / region._label_image.shape[0],  # noqa: SLF001
            )
            for region in regions
        }
        self._mark_to_coordinate = label_to_coord

    def _format_label(self, label_num: int) -> str | int:
        """Format a label number to a string.

        This is used to convert the label number to a string for display.
        """
        if self._mark_type == "alphabet":
            return self.alphabet[label_num - 1]
        if self._mark_type == "number":
            return label_num
        raise ValueError(f"Invalid mark type: {self._mark_type}. Must be 'alphabet' or 'number'.")
