from collections.abc import Generator
from types import MappingProxyType

from gptnt.processors.labels.types import DrawData, RegionProperties


def venn(regions: list[RegionProperties], *, offset: int = 25) -> Generator[DrawData]:
    """Generate draw data for venn module."""
    sorted_regions = sorted(regions, key=lambda region: region.bbox[1])
    venn_horizontal_offset_mapping = MappingProxyType({0: -5, 1: -5, 2: 0, 3: 0, 4: 0, 5: 0})  # noqa: WPS221

    for wire_idx, region in enumerate(sorted_regions):
        # bottom-left
        coord = (region.bbox[2] + offset, region.bbox[3])

        coord = (coord[0], coord[1] + venn_horizontal_offset_mapping.get(wire_idx, -10))

        yield DrawData(coord, region)
