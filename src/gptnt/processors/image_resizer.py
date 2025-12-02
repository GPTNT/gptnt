from dataclasses import dataclass

from PIL.Image import Image, Resampling
from structlog import get_logger

logger = get_logger()


@dataclass(kw_only=True, frozen=True)
class ImageResizer:
    """Helper class for resizing provided images to specified dimensions."""

    target_width: int
    target_height: int
    resampling_method: Resampling | int = Resampling.NEAREST

    def resize_image(self, image: Image) -> Image:
        """Resize image to target specifications."""
        return image.resize((self.target_width, self.target_height), self.resampling_method)
