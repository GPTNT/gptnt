from collections.abc import Generator

import numpy as np

from gptnt.processors.labels.types import (
    Coordinates,
    DrawData,
    NumberBoxDimensions,
    RegionProperties,
)

VERTICAL_OFFSET = 5


def _resolve_overlaps(
    coords: list[Coordinates], box_dims: NumberBoxDimensions, center_label_index: int
) -> list[Coordinates]:
    """Resolve overlaps between labels by pushing them apart."""
    new_coords = coords.copy()

    # move upwards from centre label
    for idx in range(center_label_index - 1, -1, -1):
        below_label = new_coords[idx + 1]
        current_label = new_coords[idx]

        # if label's top side overlaps with next label's bottom side
        if (
            current_label.y_pos + box_dims.height + box_dims.padding * 2 + box_dims.space_between
            > below_label.y_pos
        ):
            # push current label upwards
            new_y = (
                current_label.y_pos
                - box_dims.height
                - box_dims.padding * 2
                - box_dims.space_between
            )
            new_coords[idx + 1] = Coordinates(y_pos=new_y, x_pos=below_label.x_pos)
    # move downwards from centre label
    for idx in range(center_label_index + 1, len(new_coords)):  # noqa: WPS518
        above_label = new_coords[idx - 1]
        current_label = new_coords[idx]

        # if label's top side overlaps with previous label's bottom side
        if (
            current_label.y_pos
            < above_label.y_pos + box_dims.height + box_dims.padding * 2 + box_dims.space_between
        ):
            # push current label downwards
            new_y = (
                current_label.y_pos
                - box_dims.height
                - box_dims.padding * 2
                - box_dims.space_between
            )
            new_coords[idx - 1] = Coordinates(y_pos=new_y, x_pos=above_label.x_pos)

    return new_coords


def wire_sequence(  # noqa: WPS210
    regions: list[RegionProperties], box_dims: NumberBoxDimensions, *, x_offset: int = 20
) -> Generator[DrawData]:
    """Generate draw data for wire sequence module."""
    # sort regions by label as coordinates are unreliable
    sorted_regions = sorted(regions, key=lambda region: region.label)

    # ideal coordinates
    ideal_coords = []
    for region in sorted_regions:
        x_coord = region.bbox[1] - box_dims.width // 2 - box_dims.padding - x_offset
        angle = np.rad2deg(region.orientation)
        y_coord = region.bbox[2] if angle < 0 else region.bbox[0]

        coord = Coordinates(y_pos=y_coord, x_pos=x_coord)
        ideal_coords.append(coord)

    # put the buttons labels above and below the region instead of to the side
    ideal_coords[0] = Coordinates(
        y_pos=sorted_regions[0].bbox[0]
        - box_dims.height // 2
        - box_dims.padding
        - VERTICAL_OFFSET,
        x_pos=int(sorted_regions[0].centroid[1]),
    )
    ideal_coords[-1] = Coordinates(
        y_pos=sorted_regions[-1].bbox[2]
        + box_dims.height // 2
        + box_dims.padding
        + VERTICAL_OFFSET,
        x_pos=int(sorted_regions[0].centroid[1]),
    )

    # only resolve overlaps for the middle labels (wire labels)
    middle_coords = ideal_coords[1:-1]
    middle_center_index = (len(middle_coords) - 1) // 2
    resolved_middle = _resolve_overlaps(
        middle_coords, box_dims, center_label_index=middle_center_index
    )
    # reconstruct full list
    resolved_coords = [ideal_coords[0], *resolved_middle, ideal_coords[-1]]

    # yield final drawing data
    for coord, region in zip(resolved_coords, sorted_regions, strict=False):
        yield DrawData((coord.y_pos, coord.x_pos), region)
