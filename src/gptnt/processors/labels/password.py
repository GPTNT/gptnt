from collections.abc import Generator

from gptnt.processors.labels.types import (
    Coordinates,
    DrawData,
    NumberBoxDimensions,
    RegionProperties,
)

# index of centre label (i.e. label that will always be ideally placed)
CENTER_LABEL = 2


def _resolve_overlaps(
    coords: list[Coordinates], box_dims: NumberBoxDimensions
) -> list[Coordinates]:
    """Resolve overlaps between labels by pushing them apart."""
    new_coords = coords.copy()

    # move left from centre label
    for idx in range(CENTER_LABEL - 1, -1, -1):
        right = new_coords[idx + 1]
        current = new_coords[idx]

        if (
            current.x_pos + box_dims.width + box_dims.padding * 2 + box_dims.space_between
            > right.x_pos
        ):
            new_x = right.x_pos - box_dims.width - box_dims.padding * 2 - box_dims.space_between
            new_coords[idx] = Coordinates(y_pos=current.y_pos, x_pos=new_x)

    # move right from centre label
    for idx in range(CENTER_LABEL + 1, len(new_coords)):  # noqa: WPS518
        left = new_coords[idx - 1]
        current = new_coords[idx]

        if (
            current.x_pos
            < left.x_pos + box_dims.width + box_dims.padding * 2 + box_dims.space_between
        ):
            new_x = left.x_pos + box_dims.width + box_dims.padding * 2 + box_dims.space_between
            new_coords[idx] = Coordinates(y_pos=current.y_pos, x_pos=new_x)

    return new_coords


def _split_rows(
    regions: list[RegionProperties],
) -> tuple[list[RegionProperties], list[RegionProperties]]:
    """Split regions into two rows based on vertical position."""
    sorted_by_y = sorted(regions, key=lambda region: region.centroid[0])
    mid_index = len(sorted_by_y) // 2
    return sorted_by_y[:mid_index], sorted_by_y[mid_index:]


def _generate_top_row_draw_data(
    regions: list[RegionProperties], box_dims: NumberBoxDimensions, y_offset: int
) -> Generator[DrawData]:
    """Generate draw data for a single row of regions."""
    sorted_regions = sorted(regions, key=lambda region: region.bbox[1])

    ideal_coords = []
    for region in sorted_regions:
        x_coord = int(region.centroid[1])
        y_coord = region.bbox[0] - box_dims.height // 2 - box_dims.padding - y_offset
        ideal_coords.append(Coordinates(y_pos=y_coord, x_pos=x_coord))

    resolved_coords = _resolve_overlaps(ideal_coords, box_dims)

    for coord, region in zip(resolved_coords, sorted_regions, strict=False):
        yield DrawData((coord.y_pos, coord.x_pos), region)


def _generate_bottom_row_draw_data(
    regions: list[RegionProperties], box_dims: NumberBoxDimensions, y_offset: int
) -> Generator[DrawData]:
    """Generate draw data for a single row of regions."""
    sorted_regions = sorted(regions, key=lambda region: region.bbox[1])

    ideal_coords = []
    for region in sorted_regions:
        x_coord = int(region.centroid[1])
        y_coord = region.bbox[2] + box_dims.height // 2 + box_dims.padding + y_offset
        ideal_coords.append(Coordinates(y_pos=y_coord, x_pos=x_coord))

    resolved_coords = _resolve_overlaps(ideal_coords, box_dims)

    for coord, region in zip(resolved_coords, sorted_regions, strict=False):
        yield DrawData((coord.y_pos, coord.x_pos), region)


def password(
    regions: list[RegionProperties], box_dims: NumberBoxDimensions, *, y_offset: int = 5
) -> Generator[DrawData]:
    """Generate draw data for venn module with two rows."""
    top_row, bottom_row = _split_rows(regions)

    yield from _generate_top_row_draw_data(top_row, box_dims, y_offset=y_offset)

    yield from _generate_bottom_row_draw_data(bottom_row, box_dims, y_offset=y_offset)
