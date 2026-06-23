from dataclasses import dataclass
from typing import Any

import cv2
from numpy.typing import NDArray
from PIL.Image import Image, Resampling
from structlog import get_logger

from gptnt.ktane.actions import RelativeCoordinate
from gptnt.players.locations import PixelLocation

logger = get_logger()


class CoordinateOutOfBoundsError(ValueError):
    """Raised when a coordinate is out of bounds."""

    def __init__(self, coordinate: PixelLocation) -> None:
        super().__init__(f"Coordinate out of bounds: {coordinate}")
        self.coordinate = coordinate


@dataclass(kw_only=True, frozen=True)
class ImageResizer:
    """Helper class for resizing provided images to specified dimensions."""

    target_width: int
    target_height: int
    resampling_method: Resampling | int = Resampling.LANCZOS

    def resize_image(
        self, image: Image, *, resampling_method_override: Resampling | int | None = None
    ) -> Image:
        """Resize image to target specifications."""
        if image.width == self.target_width and image.height == self.target_height:
            return image

        return image.resize(
            (self.target_width, self.target_height),
            resampling_method_override or self.resampling_method,
        )

    def resize_array(
        self, array: NDArray[Any], *, resampling_method_override: Resampling | int | None = None
    ) -> NDArray[Any]:
        """Resize a numpy array representing an image to target specifications."""
        return cv2.resize(
            array,
            (self.target_width, self.target_height),
            interpolation=resampling_method_override or self.resampling_method,
        )

    def convert_absolute_to_relative(self, *, coordinate: PixelLocation) -> RelativeCoordinate:
        """Convert absolute coordinate to relative coordinate based on target dimensions."""
        if not (0 <= coordinate.x < self.target_width) or not (
            0 <= coordinate.y < self.target_height
        ):
            raise CoordinateOutOfBoundsError(coordinate)

        relative_x = coordinate.x / self.target_width
        relative_y = coordinate.y / self.target_height
        return RelativeCoordinate(x_pos=relative_x, y_pos=relative_y)
