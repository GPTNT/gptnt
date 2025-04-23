from collections.abc import Generator
from types import MappingProxyType

import structlog

from gptnt.processors.labels.types import DrawData, RegionProperties

BOTTOM_Y_OFFSETS = MappingProxyType({0: 20, 1: 15, 3: 10, 4: 20})
SUBMIT_Y_OFFSET = 20
SUBMIT_X_OFFSET = 13

PASSWORD_REGIONS = 11
log = structlog.get_logger()


def password(regions: list[RegionProperties], *, offset: int = 6) -> Generator[DrawData]:
    """Annotate the password module with labels."""
    if len(regions) != PASSWORD_REGIONS:
        log.warning("Password should have {PASSWORD_REGIONS} regions, but got %d", len(regions))
    top_5, bottom_5, submit_button = _categorize_buttons(regions)

    for button_idx, region in enumerate(regions):
        if region in top_5:
            coord = _calculate_coord(
                region=region, offset=offset, button_idx=button_idx, is_top=True, is_submit=False
            )
        elif region in bottom_5:
            coord = _calculate_coord(
                region=region, offset=0, button_idx=button_idx, is_top=False, is_submit=False
            )
        else:
            coord = _calculate_coord(
                region=region, offset=SUBMIT_Y_OFFSET, button_idx=0, is_submit=True, is_top=False
            )
        yield DrawData(coord, region)


def _categorize_buttons(
    regions: list[RegionProperties],
) -> tuple[list[RegionProperties], list[RegionProperties], list[RegionProperties]]:
    """Categorize regions into top, bottom, and submit buttons."""
    sorted_left_to_right = sorted(regions, key=lambda region: region.bbox[0])

    # Get top 5 by x, then sort by y (bbox[1])
    top_5 = sorted(sorted_left_to_right[:5], key=lambda region: region.bbox[1])

    # Get bottom 5 (second-to-last 5) by x, then sort by y
    bottom_5 = sorted(sorted_left_to_right[-6:-1], key=lambda region: region.bbox[1])  # noqa: WPS221

    # Get the region with the largest x value
    submit_button = [sorted_left_to_right[-1]]

    return top_5, bottom_5, submit_button


def _calculate_coord(
    *, region: RegionProperties, offset: int, button_idx: int, is_top: bool, is_submit: bool
) -> tuple[int, int]:
    """Calculate the coordinates for a button."""
    coord = (region.bbox[2], region.bbox[1])
    max_coord = region.coords[:, 0].max()
    min_coord = region.coords[:, 0].min()
    region_height = max_coord - min_coord

    if is_submit:
        return (coord[0] + region_height + SUBMIT_Y_OFFSET, coord[1] + SUBMIT_X_OFFSET)

    if is_top:
        adjustments = {
            4: (region_height - offset, 25),
            3: (region_height - (6 * offset), 10),
            2: (region_height - (6 * offset), 0),
            1: (region_height - (6 * offset), -10),
            0: (region_height - (6 * offset), -20),
        }
    else:
        adjustments = {
            4: (region_height - BOTTOM_Y_OFFSETS.get(4), 25),
            3: (region_height + BOTTOM_Y_OFFSETS.get(3), 15),
            0: (region_height - BOTTOM_Y_OFFSETS.get(0), -15),
            1: (region_height + BOTTOM_Y_OFFSETS.get(1), -30),
        }

    adjustment = adjustments.get(button_idx, (region_height + 10, -15))
    return (coord[0] + adjustment[0], coord[1] + adjustment[1])
