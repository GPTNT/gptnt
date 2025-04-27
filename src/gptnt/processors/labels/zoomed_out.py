from collections.abc import Generator

from gptnt.processors.labels.position import get_furthest_point_from_center
from gptnt.processors.labels.types import DrawData, NumberBoxDimensions, RegionProperties


def zoomed_out(
    regions: list[RegionProperties], _: NumberBoxDimensions, *, offset: int = 10
) -> Generator[DrawData]:
    """Annotate the zoomed out view of the bomb with labels."""
    for region in regions:
        coord = get_furthest_point_from_center(region, offset=offset)
        yield DrawData(coord, region)
