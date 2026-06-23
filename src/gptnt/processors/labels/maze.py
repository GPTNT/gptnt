from collections.abc import Generator

import structlog

from gptnt.processors.labels.position import get_region_height
from gptnt.processors.labels.types import DrawData, NumberBoxDimensions, RegionProperties

MAZE_REGIONS = 4
TOP_X_OFFSET = 5
BOTTOM_X_OFFSET = 0
LEFT_X_OFFSET = -20
RIGHT_X_OFFSET = 20
TOP_Y_OFFSET = -15
BOTTOM_Y_OFFSET = 10
LEFT_Y_OFFSET = -18
RIGHT_Y_OFFSET = -18
log = structlog.get_logger()


def maze_get_buttons(
    regions: list[RegionProperties],
) -> tuple[RegionProperties, RegionProperties, RegionProperties, RegionProperties]:
    """Get the buttons for the maze module."""
    # The left button is the region with the lowest x coordinate
    buttons_sorted_by_x_coord: list[RegionProperties] = sorted(
        regions, key=lambda region: region.bbox[1]
    )
    buttons_sorted_by_y_coord: list[RegionProperties] = sorted(
        regions, key=lambda region: region.bbox[0]
    )

    left_button = buttons_sorted_by_x_coord[0]
    right_button = buttons_sorted_by_x_coord[-1]
    top_button = buttons_sorted_by_y_coord[0]
    bottom_button = buttons_sorted_by_y_coord[-1]

    return left_button, right_button, top_button, bottom_button


def calculate_maze_button_coordinates(
    region: RegionProperties,
    region_height: int,
    left_button: RegionProperties,
    right_button: RegionProperties,
    top_button: RegionProperties,
    bottom_button: RegionProperties,
) -> tuple[int, int]:
    """Calculate the coordinates for a maze button."""
    coord = region.coords[region.coords[:, 0].argmax()]
    if region is left_button:
        return (coord[0] + region_height + LEFT_Y_OFFSET, coord[1] + LEFT_X_OFFSET)
    if region is right_button:
        return (coord[0] + region_height + RIGHT_Y_OFFSET, coord[1] + RIGHT_X_OFFSET)
    if region is top_button:
        return (coord[0] - region_height + TOP_Y_OFFSET, coord[1] + TOP_X_OFFSET)
    if region is bottom_button:
        return (coord[0] + region_height + BOTTOM_Y_OFFSET, coord[1] + BOTTOM_X_OFFSET)
    return coord


def maze(regions: list[RegionProperties], _: NumberBoxDimensions) -> Generator[DrawData]:
    """Annotate the maze module with labels."""
    if len(regions) != MAZE_REGIONS:
        log.warning(f"Maze should have {MAZE_REGIONS} regions, but got %d", len(regions))
    left_button, right_button, top_button, bottom_button = maze_get_buttons(regions)
    for region in regions:
        region_height = get_region_height(region)
        coord = calculate_maze_button_coordinates(
            region, region_height, left_button, right_button, top_button, bottom_button
        )
        yield DrawData(coord, region)
