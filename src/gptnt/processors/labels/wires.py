from collections.abc import Generator

from gptnt.processors.labels.types import (
    Coordinates,
    DrawData,
    NumberBoxDimensions,
    RegionProperties,
)

OVERCROWDING_THRESHOLD = 4


def resolve_overlaps(
    coords: list[Coordinates], box_dims: NumberBoxDimensions, center_label_index: int
) -> list[Coordinates]:
    """Resolve overlaps between labels by pushing them apart."""
    new_coords = coords.copy()

    # move upwards from centre label
    for idx in range(center_label_index - 1, -1, -1):
        below_label = new_coords[idx + 1]
        current_label = new_coords[idx]

        # if label's top side overlaps with next label's bottom side
        if (
            current_label.y_pos + box_dims.height + box_dims.padding * 2 + box_dims.space_between
            > below_label.y_pos
        ):
            # push current label upwards
            new_y = (
                below_label.y_pos - box_dims.height - box_dims.padding * 2 - box_dims.space_between
            )
            new_coords[idx] = Coordinates(y_pos=new_y, x_pos=current_label.x_pos)

    # move downwards from centre label
    for idx in range(center_label_index + 1, len(new_coords)):  # noqa: WPS518
        above_label = new_coords[idx - 1]
        current_label = new_coords[idx]

        # if label's top side overlaps with previous label's bottom side
        if (
            current_label.y_pos
            < above_label.y_pos + box_dims.height + box_dims.padding * 2 + box_dims.space_between
        ):
            # push current label downwards
            new_y = (
                above_label.y_pos + box_dims.height + box_dims.padding * 2 + box_dims.space_between
            )
            new_coords[idx] = Coordinates(y_pos=new_y, x_pos=current_label.x_pos)

    return new_coords


def wires(
    regions: list[RegionProperties], box_dims: NumberBoxDimensions, *, x_offset: int = -7
) -> Generator[DrawData]:
    """Generate draw data for venn module."""
    sorted_regions = sorted(regions, key=lambda region: region.bbox[0])

    number_of_wires = len(sorted_regions)

    # ideal coordinates
    ideal_coords = []
    for region in sorted_regions:
        x_coord = region.bbox[1] - box_dims.width // 2 - box_dims.padding + x_offset
        y_coord = int(region.centroid[0])

        coord = Coordinates(y_pos=y_coord, x_pos=x_coord)
        ideal_coords.append(coord)

    # if too many wires, put a couple above and below the wires
    if number_of_wires > OVERCROWDING_THRESHOLD:
        ideal_coords[0] = Coordinates(
            y_pos=sorted_regions[0].bbox[2] - box_dims.height // 2 - box_dims.padding,
            x_pos=int(sorted_regions[0].centroid[1]),
        )
        ideal_coords[-1] = Coordinates(
            y_pos=sorted_regions[-1].bbox[2] + box_dims.height // 2 + box_dims.padding,
            x_pos=int(sorted_regions[0].centroid[1]),
        )

    # index of centre label (i.e. label that will always be ideally placed)
    center_label_index = (number_of_wires - 1) // 2  # rounds up when n is even

    # resolve overlaps starting from 3rd wire (index 2)
    resolved_coords = resolve_overlaps(
        ideal_coords, box_dims, center_label_index=center_label_index
    )

    # yield final drawing data
    for coord, region in zip(resolved_coords, sorted_regions, strict=False):
        yield DrawData((coord.y_pos, coord.x_pos), region)
