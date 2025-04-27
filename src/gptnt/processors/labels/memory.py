from collections.abc import Generator

import structlog

from gptnt.processors.labels.types import (
    Coordinates,
    DrawData,
    NumberBoxDimensions,
    RegionProperties,
)

MEMORY_REGIONS = 4
log = structlog.get_logger()

# index of centre label (i.e. label that will always be ideally placed)
CENTER_LABEL = 2


def resolve_overlaps(
    coords: list[Coordinates], box_dims: NumberBoxDimensions
) -> list[Coordinates]:
    """Resolve overlaps between labels by pushing them apart."""
    new_coords = coords.copy()

    # move left from centre label
    for idx in range(CENTER_LABEL - 1, -1, -1):
        right = new_coords[idx + 1]
        current = new_coords[idx]

        # if label's right side overlaps with next label's left side
        if (
            current.x_pos + box_dims.width + box_dims.padding * 2 + box_dims.space_between
            > right.x_pos
        ):
            # push current label to the left
            new_x = right.x_pos - box_dims.width - box_dims.padding * 2 - box_dims.space_between
            new_coords[idx] = Coordinates(y_pos=current.y_pos, x_pos=new_x)

    # move right from centre label
    for idx in range(CENTER_LABEL + 1, len(new_coords)):  # noqa: WPS518
        left = new_coords[idx - 1]
        current = new_coords[idx]

        # if label's left side overlaps with previous label's right side
        if (
            current.x_pos
            < left.x_pos + box_dims.width + box_dims.padding * 2 + box_dims.space_between
        ):
            # push current label to the right
            new_x = left.x_pos + box_dims.width + box_dims.padding * 2 + box_dims.space_between
            new_coords[idx] = Coordinates(y_pos=current.y_pos, x_pos=new_x)

    return new_coords


def memory(
    regions: list[RegionProperties], box_dims: NumberBoxDimensions, *, y_offset: int = 5
) -> Generator[DrawData]:
    """Generate draw data for venn module."""
    sorted_regions = sorted(regions, key=lambda region: region.bbox[1])

    # ideal coordinates
    ideal_coords = []
    for region in sorted_regions:
        x_coord = int(region.centroid[1])
        y_coord = region.bbox[2] + box_dims.height // 2 + box_dims.padding + y_offset

        coord = Coordinates(y_pos=y_coord, x_pos=x_coord)
        ideal_coords.append(coord)

    # resolve overlaps starting from 3rd wire (index 2)
    resolved_coords = resolve_overlaps(ideal_coords, box_dims)

    # yield final drawing data
    for coord, region in zip(resolved_coords, sorted_regions, strict=False):
        yield DrawData((coord.y_pos, coord.x_pos), region)
