from collections.abc import Generator
from types import MappingProxyType

from gptnt.processors.labels.types import DrawData, RegionProperties

BOTTOM_WIRE_INDEX = 5
TOP_WIRE_INDEX = 0
BOTTOM_WIRE_X_OFFSET = 30
TOP_WIRE_X_OFFSET = 40

WIRE_Y_OFFSETS_FIRST_3_WIRES = {0: 35, 1: 20, 2: 0}
WIRE_Y_OFFSETS_SECOND_3_WIRES = {3: -10, 4: -30, 5: -20}
WIRE_Y_OFFSETS = MappingProxyType(
    {**WIRE_Y_OFFSETS_FIRST_3_WIRES, **WIRE_Y_OFFSETS_SECOND_3_WIRES}
)


def wire_sequence(regions: list[RegionProperties], *, x_offset: int = 20) -> Generator[DrawData]:
    """Annotate the wires module with labels."""
    # Sorted from top to bottom
    regions = sorted(regions, key=lambda region: region.bbox[0])

    for wire_idx, region in enumerate(regions):
        # bottom-left of coord
        y_coord, x_coord = (region.bbox[2], region.bbox[1] - x_offset)
        coord = 0

        if wire_idx == BOTTOM_WIRE_INDEX:
            coord = (y_coord - WIRE_Y_OFFSETS.get(wire_idx), x_coord + BOTTOM_WIRE_X_OFFSET)
        elif wire_idx == TOP_WIRE_INDEX:
            coord = (y_coord - WIRE_Y_OFFSETS.get(wire_idx), x_coord + TOP_WIRE_X_OFFSET)
        else:
            coord = (y_coord - WIRE_Y_OFFSETS.get(wire_idx), x_coord)

        yield DrawData(coord, region)
