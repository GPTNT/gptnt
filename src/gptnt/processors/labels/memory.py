from collections.abc import Generator

import structlog

from gptnt.processors.labels.types import DrawData, NumberBoxDimensions, RegionProperties

MEMORY_REGIONS = 4
log = structlog.get_logger()


def calculate_memory_label_coordinates(
    region: RegionProperties,
    far_left: RegionProperties,
    far_right: RegionProperties,
    middle_left: RegionProperties,
    middle_right: RegionProperties,
    offset: int,
) -> tuple[int, int]:
    """Calculate label coordinates for memory regions."""
    coord = region.coords[region.coords[:, 0].argmax()]
    y_offset = 10

    y_coord = coord[0] + y_offset
    x_coord = coord[1]

    if region is far_left:
        offset = -10
        return (y_coord, x_coord - offset)
    if region is far_right:
        offset = 10
        return (y_coord, x_coord + offset)
    if region is middle_left:
        offset = -10
        return (y_coord, x_coord - offset)
    if region is middle_right:
        offset = 8
        return (y_coord, x_coord + offset)

    return coord


def memory(
    regions: list[RegionProperties], _: NumberBoxDimensions, *, offset: int = -5
) -> Generator[DrawData]:
    """Annotate the memory module with labels."""
    if len(regions) != MEMORY_REGIONS:
        log.warning(f"Memory should have {MEMORY_REGIONS} regions, but got %d", len(regions))

    sorted_regions = sorted(regions, key=lambda region: region.bbox[1])
    far_left = sorted_regions[0]
    far_right = sorted_regions[-1]
    middle_left = sorted_regions[1]
    middle_right = sorted_regions[-2]

    for region in regions:
        coord = calculate_memory_label_coordinates(
            region, far_left, far_right, middle_left, middle_right, offset
        )
        yield DrawData(coord, region)
