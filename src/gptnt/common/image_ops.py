import base64
from io import BytesIO
from typing import NamedTuple

from PIL import Image


class ImageDimensions(NamedTuple):
    """Dimensions of an image (width, height)."""

    width: int
    height: int


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
