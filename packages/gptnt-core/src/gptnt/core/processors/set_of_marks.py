import itertools
import math
import string
from collections.abc import Callable, Generator, Mapping
from dataclasses import dataclass
from functools import lru_cache, partial
from types import MappingProxyType
from typing import ClassVar, Literal

import cv2
import logfire
import numpy as np
import structlog
from numpy.typing import NDArray
from skimage.measure import regionprops

from gptnt.core.ktane.actions import RelativeCoordinate
from gptnt.core.ktane.state.modules import KtaneComponent
from gptnt.core.players.locations import SetOfMarksLocation
from gptnt.core.processors.labels.color import get_region_color
from gptnt.core.processors.labels.drawing import (
    AnnotationBackgroundParams,
    AnnotationTextParams,
    draw_annotation,
    draw_mask_on_image,
)
from gptnt.core.processors.labels.highlighting import highlight_module_with_square
from gptnt.core.processors.labels.keypad import keypad
from gptnt.core.processors.labels.maze import maze
from gptnt.core.processors.labels.memory import memory
from gptnt.core.processors.labels.morse import morse_code
from gptnt.core.processors.labels.ordering import (
    get_centered_stepped_coordinate,
    relabel_regions_in_reading_order,
)
from gptnt.core.processors.labels.password import password
from gptnt.core.processors.labels.simon import simon
from gptnt.core.processors.labels.types import (  # noqa: WPS235
    Coordinates,
    DrawData,
    NumberBoxDimensions,
    RegionProperties,
    RGBArray,
)
from gptnt.core.processors.labels.venn import venn
from gptnt.core.processors.labels.whos_on_first import whos_on_first
from gptnt.core.processors.labels.wire_sequence import wire_sequence
from gptnt.core.processors.labels.wires import wires
from gptnt.core.processors.labels.zoomed_out import zoomed_out

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

    def __init__(self, location: SetOfMarksLocation | RelativeCoordinate) -> None:
        super().__init__(f"Invalid location: {location}")
        self.mark_id = location


@logfire.instrument("Convert colourful segmentation to labelled image", extract_args=False)
def convert_colorful_segm_to_labeled(image_as_array: RGBArray) -> NDArray[np.uint8]:  # noqa: WPS210
    """Convert colourful segmentation to a labelled image.

    Input shape: (height, width, channels = 3)
    Output shape: (height, width)

    ---

    ## How to handle anti-aliasing in segmentation masks

    There's a big pain with this process and that's the anti-aliasing that exists when we are
    dealing with segmentation masks. When we render the segmentation mask, the pixels at the
    boundaries get blended between the colour of the segment and black (0,0,0). The function for
    the blending is basically:

        p = alpha * [R, G, B],   0 < alpha ≤ 1

    This can result in hundreds of slightly different pixel values for the same colour/segment. So
    we need to collapse them down into a single colour so we can properly label them.

    Naively, we could convert to HSV and force S=1 and V=1 for every non-black pixel and then
    convert it back. This works because we just then have the hue values to differentiate it, but
    this comes at the cost of needing to convert back and forth, which takes longer (like 500ms and
    we need this function to be as fast as possible). So why is the hue preserved and is that
    something we can understand more to avoid the hsv conversion?

    HSV hue for any pixel is computed from channel *ratios*, not absolute values. For the R-max
    sector as an example:

        H = (G - B) / (max(R,G,B) - min(R,G,B))

    When we plug in the blended pixel, the alpha cancels out from the top and bottom, meaning that
    H is identical to the original. This means that the "set S=1, V=1, and convert back" is
    geometrically the same as doing a simple min-max stretch in RGB space:

        normalised_i = (channel_i - min) / (max - min) * 255

    And since it cancels here too, every blended pixel maps to the same normalised uint8 triplet,
    which is what we want.

    Some edge cases to consider:
        - Pure black pixels (0,0,0) will stay the same and be correctly labelled as background.
        - Grey pixels will be a problem, BUT since that's not a valid segment colour (we know this
          from the mod), we don't need to worry about it.
    """
    # flatten image and group colour channels together
    height, width, color_chan = image_as_array.shape
    # shape: (height * width, channels = 3)
    flattened = image_as_array.reshape(-1, color_chan)

    flat_f = flattened.astype(np.float32)
    min_val = flat_f.min(axis=1, keepdims=True)  # (N, 1)
    max_val = flat_f.max(axis=1, keepdims=True)  # (N, 1)
    col_range = max_val - min_val

    # Normalise to min=0 / max=255 without any HSV conversion.
    # For anti-aliased pixels (pure colour blended with black) alpha cancels out,
    # so every blend level maps to the same uint8 triplet.
    # Fallback denom handles degenerate grey pixels (col_range == 0, max > 0).
    denom = np.where(col_range > 0, col_range, np.maximum(max_val, 1.0))
    fixed_rgb = np.where(max_val > 0, (flat_f - min_val) / denom * 255.0, 0).astype(np.uint8)  # noqa: WPS221

    # Pack 3x uint8 → uint32 so np.unique works on a 1-D array (much faster).
    packed = (
        fixed_rgb[:, 0].astype(np.uint32) << 16
        | fixed_rgb[:, 1].astype(np.uint32) << 8
        | fixed_rgb[:, 2].astype(np.uint32)
    )
    _, inverse = np.unique(packed, return_inverse=True)

    # reshape the labels to image dimensions again
    # shape: (height, width)
    return inverse.reshape(height, width).astype(np.uint8)


@logfire.instrument("Get region properties", extract_args=False)
def get_region_properties(labeled_image: NDArray[np.uint8]) -> list[RegionProperties]:
    """Extract region properties from a labelled image."""
    props = regionprops(labeled_image)
    props = [props for props in props if props.area > PROPS_AREA_THRESHOLD]
    return props


def extract_and_order_regions(
    colorful_image: RGBArray, zoomed_in_component: KtaneComponent | None
) -> tuple[RGBArray, list[RegionProperties]]:
    """Extract regions from a colourful segmentation image."""
    labeled_segmentation = convert_colorful_segm_to_labeled(colorful_image)
    regions = get_region_properties(labeled_segmentation)
    labeled_segmentation, regions = relabel_regions_in_reading_order(
        labeled_segmentation, regions, zoomed_in_component=zoomed_in_component
    )
    return labeled_segmentation, regions


def convert_to_grayscale(image: RGBArray) -> RGBArray:
    """Convert an image to grayscale while maintaining 3 channels."""
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    grayscale = cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)
    return np.asarray(grayscale, dtype=np.uint8)


@dataclass
class MaskDrawingParams:
    """Parameters for drawing masks on the image."""

    mask_thickness: int
    soft_mask_alpha: float
    bw_outside_mask: bool

    mask_highlight_size: int | None = None
    # Minimum size of the square to highlight the module


@logfire.instrument("Draw region masks", extract_args=["zoomed_in_component", "drawing_params"])
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
        self.mark_to_coordinate: dict[SetOfMarksLocation, RelativeCoordinate] = {}

    def reset(self) -> None:
        """Reset the mark to coordinate mapping."""
        self.mark_to_coordinate = {}

    @logfire.instrument("Extract regions", extract_args=["zoomed_in_component"])
    def extract_regions(
        self, colorful_image: RGBArray, zoomed_in_component: KtaneComponent | None
    ) -> tuple[RGBArray, list[RegionProperties]]:
        """Extract regions from a colourful segmentation image."""
        labeled_segmentation, regions = extract_and_order_regions(
            colorful_image, zoomed_in_component=zoomed_in_component
        )
        self._update_mark_to_coordinate_mapping(regions, zoomed_in_component=zoomed_in_component)
        return labeled_segmentation, regions

    @logfire.instrument("Run Set of Marks Handler", extract_args=["zoomed_in_component"])
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

    def convert_mark_to_coordinate(self, *, mark_id: SetOfMarksLocation) -> RelativeCoordinate:
        """Convert a mark ID to a relative coordinate."""
        if mark_id not in self.mark_to_coordinate:
            _logger.warning(
                "Mark ID not found in mapping", mark_id=mark_id, mapping=self.mark_to_coordinate
            )
            raise InvalidMarkLocationError(mark_id)
        return self.mark_to_coordinate[mark_id]

    def coordinate_to_mark(self, *, coordinate: RelativeCoordinate) -> SetOfMarksLocation:
        """Convert a relative coordinate to a mark ID."""
        distances = {}
        for mark_id, coord in self.mark_to_coordinate.items():
            distance = math.sqrt(
                (coord.x_pos - coordinate.x_pos) ** 2 + (coord.y_pos - coordinate.y_pos) ** 2
            )
            distances[mark_id] = distance
        closest_mark = min(distances, key=distances.get)  # pyright: ignore[reportCallIssue, reportArgumentType]
        return closest_mark

    @logfire.instrument("Draw labels", extract_args=["module"])
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

    @logfire.instrument("Update mark to coordinate mapping", extract_args=["zoomed_in_component"])
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
        self.mark_to_coordinate = label_to_coord

    def _format_label(self, label_num: int) -> str | int:
        """Format a label number to a string.

        This is used to convert the label number to a string for display.
        """
        if self._mark_type == "alphabet":
            return self.alphabet[label_num - 1]
        if self._mark_type == "number":
            return label_num
        raise ValueError(f"Invalid mark type: {self._mark_type}. Must be 'alphabet' or 'number'.")
