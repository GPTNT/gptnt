from PIL.Image import Image, Resampling
from src.gptnt.common.logger import configure_logging
from structlog import get_logger

configure_logging()
logger = get_logger()


class ImageResizer:
    """Helper class for resizing provided images to specified dimensions."""

    def __init__(self, target_width: int, target_height: int) -> None:
        self.target_width = target_width
        self.target_height = target_height

    def resize_image(self, image: Image) -> Image:
        """Resize provided image to class specifications."""
        if image.height <= self.target_height or image.width <= self.target_width:
            logger.warning(
                f"Provided image ({image.size}) is smaller than target ({self.target_width}, {self.target_height})."
            )
            return image

        # Use super-quick nearest resampling https://pillow.readthedocs.io/en/stable/handbook/concepts.html#filters-comparison-table
        return image.resize((self.target_width, self.target_height), Resampling.NEAREST)
