from collections.abc import Sequence
from typing import TypedDict, cast

import logfire
import numpy as np
from skimage.measure import regionprops
from structlog import get_logger

from gptnt.ktane.state.modules import KtaneComponent
from gptnt.processors.labels.types import RegionProperties, RGBArray

_logger = get_logger()


class RegionData(TypedDict):
    """TypedDict for region data used in ordering regions."""

    label: int
    centroid_y: float
    centroid_x: float
    min_y: int
    max_y: int
    height: int


def _check_row_overlap(r1: RegionData, r2: RegionData, *, threshold: float = 0.5) -> bool:
    """Check if two regions belong in the same row based on vertical overlap."""
    smallest_max = min(r1["max_y"], r2["max_y"])
    largest_min = max(r1["min_y"], r2["min_y"])
    overlap_height = smallest_max - largest_min
    if overlap_height <= 0:
        return False

    min_height = min(r1["height"], r2["height"])
    return (overlap_height / min_height) >= threshold


def get_centered_stepped_coordinate(region: RegionProperties) -> tuple[float, float]:
    """Returns (x, y) coordinate within region, stepping in from left before calculating y.

    - x = step_in from leftmost x (or closest available)
    - y = mean y of pixels at that x
    """
    coords = region.coords
    all_xs = coords[:, 1]
    unique_xs_sorted = np.sort(np.unique(all_xs))

    if len(unique_xs_sorted) == 0:
        _logger.warning("No unique x coordinates found in region, returning centroid.")
        x_coord = region.centroid[1]
        y_coord = region.centroid[0]
    else:
        x_coord = unique_xs_sorted[len(unique_xs_sorted) // 6]
        # Now get all y values at that x
        ys_at_x = coords[coords[:, 1] == x_coord][:, 0]
        if len(ys_at_x) == 0:
            _logger.warning("No y coordinates found at stepped x, using centroid instead.")
            x_coord = region.centroid[1]
            y_coord = region.centroid[0]
        else:
            # Use median to select a y value that is part of the regions
            y_coord = float(np.median(ys_at_x))

    return y_coord, x_coord


def order_regions_reading_order(  # noqa: WPS231
    regions: Sequence[RegionProperties],
    image_shape: tuple[int, int],
    zoomed_in_component: KtaneComponent | None,
) -> list[int]:
    """Orders region labels in reading order (left-to-right, top-to-bottom).

    For image shape, it is (height, width).
    """
    if not regions:
        return []

    region_data = []
    for region in regions:
        if zoomed_in_component == KtaneComponent.wire_sequence:
            coords = get_centered_stepped_coordinate(region)
        else:
            coords = region.centroid

        region_data.append(
            RegionData(
                label=region.label,
                centroid_y=coords[0],
                centroid_x=coords[1],
                min_y=max(0, region.bbox[0]),
                max_y=min(region.bbox[2], image_shape[0]),
                height=max(0, region.bbox[2] - region.bbox[0]),
            )
        )

    rows: list[list[RegionData]] = []
    for region in sorted(region_data, key=lambda row: row["centroid_y"]):
        added_to_row = False

        if zoomed_in_component is not KtaneComponent.wire_sequence:
            for row in rows:
                if any(_check_row_overlap(region, other) for other in row):
                    row.append(region)
                    added_to_row = True
                    break

        if not added_to_row:
            rows.append([region])

    rows = sorted(rows, key=lambda row: sum(r["centroid_y"] for r in row) / len(row))  # noqa: WPS111, WPS221, WPS441

    for row in rows:
        row.sort(key=lambda row: row["centroid_x"])

    return [region["label"] for row in rows for region in row]  # noqa: WPS441


@logfire.instrument("Relabel Regions", extract_args=["zoomed_in_component"])
def relabel_regions_in_reading_order(
    labeled_image: RGBArray,
    regions: list[RegionProperties],
    zoomed_in_component: KtaneComponent | None,
) -> tuple[RGBArray, list[RegionProperties]]:
    """Relabels both the labeled image and region properties in reading order.

    This function:
    1. Determines the reading order of the existing regions
    2. Creates a mapping from old labels to new sequential labels
    3. Updates the labeled image with new labels
    4. Regenerates region properties with the new labels

    Args:
        labeled_image: The labeled image array
        regions: List of RegionProperties objects from the original labeled image
        zoomed_in_component: Do not consider overlapping wires as being on the same row if component is wire_sequence

    Returns:
        Tuple containing:
        - Updated labeled image with sequential labels in reading order
        - New list of RegionProperties objects corresponding to the updated labels
    """
    if not regions:
        _logger.warning("No regions found in the labeled image.")
        return labeled_image, []

    # Get the reading order of the current labels
    ordered_labels = order_regions_reading_order(
        regions,
        image_shape=cast("tuple[int, int]", labeled_image.shape),
        zoomed_in_component=zoomed_in_component,
    )

    # Create mapping from old labels to new sequential labels (starting from 1)
    label_mapping = {old_label: new_label for new_label, old_label in enumerate(ordered_labels, 1)}

    # Create a mapping dictionary with 0 (background) mapping to 0
    full_mapping = {0: 0}
    full_mapping.update(label_mapping)

    # Create a lookup array for vectorized relabeling
    max_label = max(label_mapping.keys())
    lookup_arr = np.zeros(max_label + 1, dtype=np.uint8)
    for old_label, new_label in full_mapping.items():
        if old_label <= max_label:  # Ensure we don't go out of bounds
            lookup_arr[old_label] = new_label

    # Apply the mapping to the labeled image using vectorized indexing
    # This is much faster than iterating through the image pixel by pixel
    new_labeled_image = lookup_arr[labeled_image]

    # Regenerate region properties with the new labels
    new_regions = regionprops(new_labeled_image)

    return new_labeled_image, new_regions
