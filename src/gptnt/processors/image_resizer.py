from typing import cast

import cv2
from src.gptnt.common.logger import configure_logging
from structlog import get_logger

from gptnt.processors.set_of_marks import RGBArray

configure_logging()
logger = get_logger()


class ImageResizer:
    """Helper class for resizing provided images to specified dimensions."""

    def __init__(self, target_width: int, target_height: int) -> None:
        self.target_width = target_width
        self.target_height = target_height

    def resize_image(self, image: RGBArray) -> RGBArray:
        """Resize provided image (as RGBArray / np.ndarray) to class specifications."""
        height, width = image.shape[:2]

        if height <= self.target_height or width <= self.target_width:
            logger.warning(
                f"Provided image ({width}, {height}) is smaller than target ({self.target_width}, {self.target_height})."
            )
            return image

        resized = cv2.resize(
            image, (self.target_width, self.target_height), interpolation=cv2.INTER_NEAREST
        )
        return cast("RGBArray", resized)
