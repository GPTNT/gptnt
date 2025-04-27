import numpy as np

from gptnt.processors.labels.types import Coordinates, RegionProperties


def get_background_corner_coords(
    coords: Coordinates, padding: int = 5, text_width: int = 0, text_height: int = 0
) -> tuple[tuple[int, int], tuple[int, int]]:
    """Get background box coordinates for label."""
    # Calculate top-left and bottom-right of background rectangle
    top_left_x = coords.x_pos - text_width // 2 - padding
    top_left_y = coords.y_pos - text_height // 2 - padding
    bottom_right_x = coords.x_pos + text_width // 2 + padding
    bottom_right_y = coords.y_pos + text_height // 2 + padding

    return (top_left_x, top_left_y), (bottom_right_x, bottom_right_y)


def get_region_height(region: RegionProperties) -> int:
    """Get the height of a region."""
    # Get the coordinates of the region
    coords = region.coords

    # Get the maximum and minimum y-coordinates
    max_y = coords[:, 0].max()
    min_y = coords[:, 0].min()

    # Calculate the height
    height = max_y - min_y

    return height


def calculate_image_center(*, region: RegionProperties) -> tuple[float, float]:
    """Calculate the center of the image."""
    img_h, img_w = region._label_image.shape[:2]  # noqa: SLF001
    return img_h / 2, img_w / 2


def find_furthest_point(
    region: RegionProperties, center_y: float, center_x: float
) -> tuple[int, int]:
    """Find the furthest point from the center."""
    y_coord = (region.coords[:, 0] - center_y) ** 2
    x_coord = (region.coords[:, 1] - center_x) ** 2
    furthest_idx = np.argmax(y_coord + x_coord)
    return region.coords[furthest_idx]


def calculate_offset_point(
    furthest_y: int, furthest_x: int, center_y: float, center_x: float, offset: int
) -> Coordinates:
    """Calculate the offset point from the furthest point."""
    dy = furthest_y - center_y
    dx = furthest_x - center_x
    norm = np.hypot(dy, dx)
    if norm != 0:
        dy /= norm
        dx /= norm
    return Coordinates(
        y_pos=round(furthest_y + dy * offset), x_pos=round(furthest_x + dx * offset)
    )


def get_furthest_point_from_center(region: RegionProperties, *, offset: int = 10) -> Coordinates:
    """Get the furthest point from the center of the image for a given region."""
    center_y, center_x = calculate_image_center(region=region)
    furthest_y, furthest_x = find_furthest_point(region, center_y, center_x)
    return calculate_offset_point(furthest_y, furthest_x, center_y, center_x, offset)
