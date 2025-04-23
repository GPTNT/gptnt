from collections.abc import Generator

import structlog

from gptnt.processors.labels.types import DrawData, RegionProperties

KEYPAD_REGIONS = 4
log = structlog.get_logger()


def keypad(regions: list[RegionProperties], *, offset: int = 30) -> Generator[DrawData]:  # noqa: WPS210
    """Annotate the keypad module with labels."""
    if len(regions) != KEYPAD_REGIONS:
        log.warning(f"Keypad should have {KEYPAD_REGIONS} regions, but got %d", len(regions))
    # Sort by minimum x (leftmost)
    sorted_regions = sorted(regions, key=lambda region: region.bbox[1])
    # two leftmost regions
    left_buttons = sorted_regions[:2]

    for region in sorted_regions:
        # Calculate center of the region
        min_row, min_col, max_row, max_col = region.bbox

        # Center coordinates
        center_row = (min_row + max_row) // 2
        center_col = (min_col + max_col) // 2

        # Apply offset to position (OpenCV uses (x, y) = (col, row))
        if region in left_buttons:
            coord = (center_row, center_col - offset)
        else:
            coord = (center_row, center_col + offset)

        # Draw the label
        yield DrawData(coord, region)
