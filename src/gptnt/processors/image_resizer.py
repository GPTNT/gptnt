from PIL.Image import Image, Resampling
from structlog import get_logger

logger = get_logger()


class ImageResizer:
    """Helper class for resizing provided images to specified dimensions."""

    def __init__(
        self,
        *,
        target_width: int,
        target_height: int,
        resampling_method: Resampling | int = Resampling.NEAREST,
    ) -> None:
        self.target_width = target_width
        self.target_height = target_height
        self.resampling_method = resampling_method

    def resize_image(self, image: Image) -> Image:
        """Resize image to target specifications."""
        return image.resize((self.target_width, self.target_height), self.resampling_method)
