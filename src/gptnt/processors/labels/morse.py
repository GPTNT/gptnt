from collections.abc import Generator

import structlog

from gptnt.processors.labels.types import DrawData, NumberBoxDimensions, RegionProperties

MORSE_REGIONS = 3
log = structlog.get_logger()


def morse_code(
    regions: list[RegionProperties], box_dims: NumberBoxDimensions, *, offset: int = 0
) -> Generator[DrawData]:
    """Annotate the morse code module with labels."""
    if len(regions) != MORSE_REGIONS:
        log.warning(f"Morse should have {MORSE_REGIONS} regions, but got %d", len(regions))

    _ = box_dims  # temporary

    for region in regions:
        # bottom-left
        coord = (region.bbox[2], region.bbox[1])
        # ensure the top of the label is the bottom of the region
        max_coord = region.coords[:, 0].max()
        min_coord = region.coords[:, 0].min()
        region_height = max_coord - min_coord
        coord = (coord[0] + region_height + offset, coord[1] + 10)

        yield DrawData(coord, region)
