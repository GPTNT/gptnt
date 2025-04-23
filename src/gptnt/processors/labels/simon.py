from collections.abc import Generator

import structlog

from gptnt.processors.labels.types import DrawData, RegionProperties

SIMON_REGIONS = 4
log = structlog.get_logger()


def simon(regions: list[RegionProperties], *, offset: int = 32) -> Generator[DrawData]:  # noqa: WPS210
    """Annotate the simon module with labels."""
    if len(regions) != SIMON_REGIONS:
        log.warning(f"Simon Says should have {SIMON_REGIONS} regions, but got %d", len(regions))
    buttons = []

    sorted_top_to_bottom = sorted(regions, key=lambda region: region.bbox[0])
    sorted_left_to_right = sorted(regions, key=lambda region: region.bbox[1])
    top_button = sorted_top_to_bottom[0]
    bottom_button = sorted_top_to_bottom[-1]
    left_button = sorted_left_to_right[0]
    right_button = sorted_left_to_right[-1]

    buttons.append(("top", top_button, (-offset, 0)))  # Move text up
    buttons.append(("left", left_button, (0, -offset)))  # Move text left
    buttons.append(("bottom", bottom_button, (offset, 0)))  # Move text down
    buttons.append(("right", right_button, (0, offset)))  # Move text right

    for _position_name, region, offset_tuple in buttons:
        # Calculate center of the region
        # Center coordinates
        center_row = (region.bbox[0] + region.bbox[2]) // 2
        center_col = (region.bbox[1] + region.bbox[3]) // 2

        # Apply offset to position (OpenCV uses (x, y) = (col, row))
        yield DrawData((center_row + offset_tuple[0], center_col + offset_tuple[1]), region)
