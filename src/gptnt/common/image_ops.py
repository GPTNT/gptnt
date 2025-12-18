import base64
from dataclasses import dataclass
from io import BytesIO

from PIL import Image


@dataclass(frozen=True)
class ImageDimensions:
    """Dimensions of an image (width, height)."""

    width: int
    height: int

    @property
    def long_side(self) -> int:
        """The length of the longer side of the image."""
        return max(self.width, self.height)

    @property
    def short_side(self) -> int:
        """The length of the shorter side of the image."""
        return min(self.width, self.height)


def load_observation_from_bytes(image: bytes | str) -> Image.Image:
    """Load an observation image from bytes.

    Observations are PNG in RGB format. If the input is a string, it is assumed to be a base64
    encoded string.
    """
    # Decode the base64 string
    if isinstance(image, str):
        image = base64.b64decode(image)
    # Load the image
    return Image.open(BytesIO(image), formats=["PNG"]).convert("RGB")
