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
    check_colors,
    get_median_colour,
)
from gptnt.processors.labels.drawing import (
    AnnotationBackgroundParams,
    AnnotationTextParams,
    draw_annotation,
)
from gptnt.processors.labels.highlighting import highlight_module_with_square
from gptnt.processors.labels.keypad import keypad
from gptnt.processors.labels.maze import maze
from gptnt.processors.labels.memory import memory
from gptnt.processors.labels.morse import morse_code
from gptnt.processors.labels.ordering import relabel_regions_in_reading_order
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


class InvalidMarkLocationError(KeyError):
    """Raised when a mark ID is not found in the coordinate mapping."""

    def __init__(self, mark_id: SetOfMarksLocation) -> None:
        super().__init__(f"Invalid mark location: {mark_id}")
        self.mark_id = mark_id


def blend_with_image(image: RGBArray, mask: RGBArray, alpha: float = 0.3) -> RGBArray:
    """Blend a mask with an image using alpha transparency."""
    blended = cv2.addWeighted(mask, alpha, image, 1 - alpha, 0)
    return np.asarray(blended, dtype=np.uint8)


def convert_colorful_segm_to_labeled(image_as_array: RGBArray) -> NDArray[np.uint8]:  # noqa: WPS210
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
    return inverse.reshape(height, width).astype(np.uint8)


def get_region_properties(labeled_image: NDArray[np.uint8]) -> list[RegionProperties]:
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
    color: tuple[Color, ...],
    thickness: int,
    soft_mask_alpha: float,
) -> tuple[RGBArray, NDArray[np.bool_]]:
    """Draw outline of a single region with optional color split for top/bottom."""
    # blank mask
    mask = np.zeros_like(image[:, :, 0])

    # get all region pixels on the mask
    for y_coord, x_coord in coords:
        mask[y_coord, x_coord] = 255

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


def is_hsv_white(hsv: tuple[float, float, float]) -> bool:
    """Check if a given HSV value is (essentially) white."""
    return hsv[1] < 0.2 and hsv[2] > 150  # noqa: WPS459 PLR2004


def is_hsv_black(hsv: tuple[float, float, float]) -> bool:
    """Check if a given HSV value is (essentially) black."""
    return hsv[1] < 0.2 and hsv[2] < 50  # noqa: WPS459 PLR2004


def handle_venn(region: RegionProperties, image: RGBArray) -> tuple[Color, ...]:
    """Check if the region is a venn diagram."""
    has_white, has_blue, has_red = check_colors(region, image)
    color_mapping = {
        (True, True, False): (WHITE, BLUE),
        (True, False, True): (WHITE, RED),
        (False, True, True): (BLUE, RED),
        (True, False, False): (WHITE,),
        (False, True, False): (BLUE,),
    }
    colors = color_mapping.get((has_white, has_blue, has_red), (RED,))
    return colors


def get_region_color(  # noqa: WPS212
    image: RGBArray, segm_image: RGBArray, region: RegionProperties, module: KtaneComponent | None
) -> tuple[Color, ...]:
    """Get the colour of a region based on the module type."""
    # Use image colours for colour dependent modules (but only wire interactables for wire modules)

    if module == KtaneComponent.venn:
        return handle_venn(region, image)

    if module in ENTIRELY_COLOR_DEPENDENT_MODULES or (
        module == KtaneComponent.wire_sequence and region.eccentricity > IS_LINE_THRESHOLD
    ):
        color = get_median_colour(region, image)

        return (color,)

    if module == KtaneComponent.wire_sequence:
        # Set the colors of the wire_sequence buttons so that they do not match one of the wires
        color = get_median_colour(region, segm_image)
        if color == RED:
            return (GREEN,)
        if color == BLUE:
            return (YELLOW,)

    # Otherwise, use segmentation image colour
    return (get_median_colour(region, segm_image),)


@dataclass
class MaskDrawingParams:
    """Parameters for drawing masks on the image."""

    mask_thickness: int
    soft_mask_alpha: float
    bw_outside_mask: bool

    mask_highlight_size: int | None = None
    # Minimum size of the square to highlight the module


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
        mask_color = get_region_color(image, segm_image, region, zoomed_in_component)

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


def get_centered_stepped_coordinate(
    region: RegionProperties, step_in: int = 10
) -> tuple[float, float]:
    """Returns (x, y) coordinate within region, stepping in from left before calculating y.

    - x = step_in from leftmost x (or closest available)
    - y = mean y of pixels at that x
    """
    coords = region.coords
    all_xs = coords[:, 1]
    unique_xs_sorted = np.sort(np.unique(all_xs))

    if len(unique_xs_sorted) == 0:
        x_coord = region.centroid[1]
        y_coord = region.centroid[0]
    else:
        leftmost_x = unique_xs_sorted[0]
        stepped_x = leftmost_x + step_in
        valid_xs = unique_xs_sorted[unique_xs_sorted >= stepped_x]
        x_coord = (
            valid_xs[0] if len(valid_xs) > 0 else unique_xs_sorted[len(unique_xs_sorted) // 2]
        )

        # Now get all y values at that x
        ys_at_x = coords[coords[:, 1] == x_coord][:, 0]
        if len(ys_at_x) == 0:
            x_coord = region.centroid[1]
            y_coord = region.centroid[0]
        else:
            y_coord = ys_at_x.mean()

    return x_coord, y_coord


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

    def extract_regions(
        self, colorful_image: RGBArray, zoomed_in_component: KtaneComponent | None
    ) -> tuple[RGBArray, list[RegionProperties]]:
        """Extract regions from a colourful segmentation image."""
        labeled_segmentation = convert_colorful_segm_to_labeled(colorful_image)
        regions = get_region_properties(labeled_segmentation)
        labeled_segmentation, regions = relabel_regions_in_reading_order(
            labeled_segmentation, regions, zoomed_in_component=zoomed_in_component
        )
        self._update_mark_to_coordinate_mapping(regions, zoomed_in_component=zoomed_in_component)
        return labeled_segmentation, regions

    def run(
        self,
        *,
        observation: RGBArray,
        colorful_image: RGBArray,
        zoomed_in_component: KtaneComponent | None = None,
    ) -> RGBArray:
        """Handle the labelling and bounding box drawing on the screenshot based on segmentation.

        Output: Annotated screenshot with bounding boxes and labels drawn.
        """
        labelled_image, regions = self.extract_regions(colorful_image, zoomed_in_component)

        if zoomed_in_component and self._mask_drawing_params.mask_highlight_size is not None:
            observation = highlight_module_with_square(
                observation,
                [region.label for region in regions],
                labelled_image,
                min_square_size=(
                    self._mask_drawing_params.mask_highlight_size,
                    self._mask_drawing_params.mask_highlight_size,
                ),
            )

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
            _logger.warning(
                "Mark ID not found in mapping", mark_id=mark_id, mapping=self._mark_to_coordinate
            )
            raise InvalidMarkLocationError(mark_id)
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
            color = get_region_color(image, segm_img, region, module)
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

    def _update_mark_to_coordinate_mapping(
        self, regions: list[RegionProperties], zoomed_in_component: KtaneComponent | None
    ) -> None:
        """Map the region label to a relative coordinate."""
        label_to_coord = {}
        for region in regions:
            if zoomed_in_component == KtaneComponent.wire_sequence:
                coords = get_centered_stepped_coordinate(region)
            else:
                coords = region.centroid

            # Normalize to [0,1] relative coordinates
            norm_x = coords[1] / region._label_image.shape[1]  # noqa: SLF001
            norm_y = coords[0] / region._label_image.shape[0]  # noqa: SLF001

            label_to_coord[self._format_label(region.label)] = RelativeCoordinate(
                x_pos=norm_x, y_pos=norm_y
            )

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
