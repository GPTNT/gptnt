from collections.abc import Generator
from types import MappingProxyType

import structlog

from gptnt.processors.labels.types import DrawData, NumberBoxDimensions, RegionProperties

log = structlog.get_logger()

RIGHT_BUTTONS_X_OFFSET = 45
RIGHT_BUTTONS_Y_OFFSETS = MappingProxyType({0: 20, 1: 10})

LEFT_BUTTONS_Y_OFFSETS = MappingProxyType({0: 25, 1: 10})

TOP_BUTTON_INDEX = 0
BOTTOM_BUTTON_INDEX = 2

WHO_FIRST_REGIONS = 6
log = structlog.get_logger()


def get_sorted_whos_on_first_regions(
    regions: list[RegionProperties],
) -> tuple[list[RegionProperties], list[RegionProperties]]:
    """Annotate the whos on first module with labels."""
    if len(regions) != WHO_FIRST_REGIONS:
        log.warning(
            f"Who's On First should have {WHO_FIRST_REGIONS} regions, but got %d", len(regions)
        )
    # The left 3 buttons sorted by their x-coordinates
    buttons_sorted_on_x_axis = sorted(regions, key=lambda region: region.bbox[1])

    left_buttons = buttons_sorted_on_x_axis[:3]
    left_buttons = sorted(left_buttons, key=lambda region: region.bbox[0])

    # The right 3 buttons sorted by their x-coordinates
    right_buttons = buttons_sorted_on_x_axis[3:]
    right_buttons = sorted(right_buttons, key=lambda region: region.bbox[0])

    return left_buttons, right_buttons


def whos_on_first(
    regions: list[RegionProperties], _: NumberBoxDimensions, *, x_offset: int = 20
) -> Generator[DrawData]:
    """Annotate the whos on first module with labels."""
    left_buttons, right_buttons = get_sorted_whos_on_first_regions(regions)

    for button_idx, region in enumerate(left_buttons):
        max_coord = region.coords[:, 0].max()
        min_coord = region.coords[:, 0].min()
        region_height = max_coord - min_coord
        y_coord, x_coord = (region.bbox[2] + region_height, region.bbox[1])

        if button_idx == TOP_BUTTON_INDEX:
            coord = (y_coord - LEFT_BUTTONS_Y_OFFSETS.get(0), x_coord - x_offset)
        elif button_idx == BOTTOM_BUTTON_INDEX:
            coord = (y_coord, x_coord - x_offset)
        else:
            coord = (y_coord - LEFT_BUTTONS_Y_OFFSETS.get(1), x_coord - x_offset)

        yield DrawData(coord, region)

    for button_idx, region in enumerate(right_buttons):
        # bottom-left
        coord = (region.bbox[2], region.bbox[1])
        # ensure the top of the label is the bottom of the region
        max_coord = region.coords[:, 0].max()
        min_coord = region.coords[:, 0].min()
        region_height = max_coord - min_coord
        y_coord, x_coord = (region.bbox[2] + region_height, region.bbox[1])
        if button_idx == TOP_BUTTON_INDEX:
            coord = (
                y_coord - RIGHT_BUTTONS_Y_OFFSETS.get(0),
                coord[1] + x_offset + RIGHT_BUTTONS_X_OFFSET,
            )

        elif button_idx == BOTTOM_BUTTON_INDEX:
            coord = (y_coord, coord[1] + x_offset + RIGHT_BUTTONS_X_OFFSET)
        else:
            coord = (
                y_coord - RIGHT_BUTTONS_Y_OFFSETS.get(1),
                coord[1] + x_offset + RIGHT_BUTTONS_X_OFFSET,
            )

        yield DrawData(coord, region)
