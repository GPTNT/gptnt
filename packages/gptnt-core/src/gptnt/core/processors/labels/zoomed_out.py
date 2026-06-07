from collections.abc import Generator

from gptnt.core.processors.labels.types import (
    Coordinates,
    DrawData,
    NumberBoxDimensions,
    RegionProperties,
)


def _split_rows(
    regions: list[RegionProperties],
) -> tuple[list[RegionProperties], list[RegionProperties]]:
    """Split regions into top and bottom rows based on vertical position."""
    # sort regions by vertical position
    sorted_by_y = sorted(regions, key=lambda region: region.centroid[0])

    # compute average vertical position
    avg_y = sum(region.centroid[0] for region in sorted_by_y) / len(sorted_by_y)

    # split into top and bottom based on whether above or below average
    top_row = [region for region in sorted_by_y if region.centroid[0] < avg_y]
    bottom_row = [region for region in sorted_by_y if region.centroid[0] >= avg_y]

    return top_row, bottom_row


def _generate_top_row_draw_data(
    regions: list[RegionProperties], box_dims: NumberBoxDimensions, offset: int
) -> Generator[DrawData]:
    """Generate draw data for a single row of regions."""
    sorted_regions = sorted(regions, key=lambda region: region.bbox[1])

    coords = []
    for region in sorted_regions:
        x_coord = region.bbox[1] - box_dims.width // 2 - box_dims.padding - offset
        y_coord = region.bbox[0] - box_dims.height // 2 - box_dims.padding - offset
        coords.append(Coordinates(y_pos=y_coord, x_pos=x_coord))

    for coord, region in zip(coords, sorted_regions, strict=False):
        yield DrawData((coord.y_pos, coord.x_pos), region)


def _generate_bottom_row_draw_data(
    regions: list[RegionProperties], box_dims: NumberBoxDimensions, offset: int
) -> Generator[DrawData]:
    """Generate draw data for a single row of regions."""
    sorted_regions = sorted(regions, key=lambda region: region.bbox[1])

    coords = []
    for region in sorted_regions:
        x_coord = region.bbox[1] - box_dims.width // 2 - box_dims.padding - offset
        y_coord = region.bbox[2] + box_dims.height // 2 + box_dims.padding + offset
        coords.append(Coordinates(y_pos=y_coord, x_pos=x_coord))

    for coord, region in zip(coords, sorted_regions, strict=False):
        yield DrawData((coord.y_pos, coord.x_pos), region)


def zoomed_out(
    regions: list[RegionProperties], box_dims: NumberBoxDimensions, *, offset: int = 0
) -> Generator[DrawData]:
    """Annotate the zoomed out view of the bomb with labels."""
    top_row, bottom_row = _split_rows(regions)

    yield from _generate_top_row_draw_data(top_row, box_dims, offset=offset)

    yield from _generate_bottom_row_draw_data(bottom_row, box_dims, offset=offset)
