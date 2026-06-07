import numpy as np
from numpy.typing import NDArray

from gptnt.core.processors.labels.types import RGBArray


def highlight_module_with_square(
    image: RGBArray,
    region_labels: list[int],
    labeled_image: RGBArray,
    min_square_size: tuple[int, int],
    padding: int = 20,
    dim_factor: float = 0.5,
) -> RGBArray:
    """Highlights a module with a square that encompasses all regions."""
    height, width = image.shape[:2]
    min_width, min_height = min_square_size

    bbox = _find_regions_bounding_box(region_labels, labeled_image)
    if bbox is None:
        bbox = _centered_box(height, width, min_width, min_height)
    bbox = _add_padding(bbox, padding, height, width)
    bbox = _ensure_min_size(bbox, min_width, min_height, height, width)

    square_mask = _create_square_mask(bbox, height, width)
    output_image = _dim_image(image, dim_factor)
    output_image = _restore_square_area(image, output_image, square_mask)

    return np.clip(output_image, 0, 255).astype(np.uint8)


def _find_regions_bounding_box(
    region_labels: list[int], labeled_image: RGBArray
) -> tuple[int, int, int, int] | None:
    min_row, min_col = float("inf"), float("inf")
    max_row, max_col = 0, 0
    found = False
    for label in region_labels:
        region_mask = labeled_image == label
        if not np.any(region_mask):
            continue
        rows, cols = np.where(region_mask)
        min_row = min(min_row, np.min(rows).item())
        min_col = min(min_col, np.min(cols).item())
        max_row = max(max_row, np.max(rows).item())
        max_col = max(max_col, np.max(cols).item())
        found = True
    if not found:
        return None
    return (int(min_row), int(min_col), int(max_row), int(max_col))


def _centered_box(
    height: int, width: int, min_width: int, min_height: int
) -> tuple[int, int, int, int]:
    center_y, center_x = height // 2, width // 2
    min_row = center_y - min_height // 2
    max_row = center_y + min_height // 2
    min_col = center_x - min_width // 2
    max_col = center_x + min_width // 2
    return (min_row, min_col, max_row, max_col)


def _add_padding(
    bbox: tuple[int, int, int, int], padding: int, height: int, width: int
) -> tuple[int, int, int, int]:
    min_row, min_col, max_row, max_col = bbox
    min_row = max(0, min_row - padding)
    min_col = max(0, min_col - padding)
    max_row = min(height, max_row + padding)
    max_col = min(width, max_col + padding)
    return (min_row, min_col, max_row, max_col)


def _ensure_min_size(
    bbox: tuple[int, int, int, int], min_width: int, min_height: int, height: int, width: int
) -> tuple[int, int, int, int]:
    min_row, min_col, max_row, max_col = bbox
    current_width = max_col - min_col
    current_height = max_row - min_row

    if current_width < min_width:
        extra = min_width - current_width
        min_col = max(0, min_col - extra // 2)
        max_col = min(width, max_col + (extra - extra // 2))
        if max_col - min_col < min_width:
            if min_col == 0:
                max_col = min(width, min_col + min_width)
            else:
                min_col = max(0, max_col - min_width)

    if current_height < min_height:
        extra = min_height - current_height
        min_row = max(0, min_row - extra // 2)
        max_row = min(height, max_row + (extra - extra // 2))
        if max_row - min_row < min_height:
            if min_row == 0:
                max_row = min(height, min_row + min_height)
            else:
                min_row = max(0, max_row - min_height)

    return (min_row, min_col, max_row, max_col)


def _create_square_mask(
    bbox: tuple[int, int, int, int], height: int, width: int
) -> NDArray[np.bool]:
    min_row, min_col, max_row, max_col = bbox
    mask = np.zeros((height, width), dtype=bool)
    mask[min_row:max_row, min_col:max_col] = True
    return mask


def _dim_image(image: RGBArray, dim_factor: float) -> NDArray[np.float32]:
    return image.astype(np.float32) * dim_factor


def _restore_square_area(
    image: RGBArray, output_image: NDArray[np.float32], square_mask: NDArray[np.bool]
) -> NDArray[np.float32]:
    for channel in range(3):
        output_image[:, :, channel][square_mask] = image[:, :, channel][square_mask]
    return output_image
