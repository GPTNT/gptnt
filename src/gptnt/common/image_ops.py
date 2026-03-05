from dataclasses import dataclass
from io import BytesIO
from typing import Annotated

import pybase64
from PIL import Image
from pydantic import BeforeValidator, PlainSerializer


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
        image = pybase64.b64decode(image)
    # Load the image
    return Image.open(BytesIO(image), formats=["PNG"]).convert("RGB")


def _parse_base64_to_bytes(data: str | bytes) -> bytes:
    """Decode base64 encoded string to bytes if string."""
    if isinstance(data, bytes):
        return data
    return pybase64.b64decode(data)


def _serialize_bytes_to_base64(data: bytes) -> str:
    """Serialize bytes to base64 encoded string for JSON."""
    return pybase64.b64encode(data).decode("utf-8")


parse_base64_to_bytes = BeforeValidator(_parse_base64_to_bytes)
serialize_bytes_to_base64 = PlainSerializer(
    _serialize_bytes_to_base64, when_used="json-unless-none"
)


PNGBytes = Annotated[bytes, parse_base64_to_bytes, serialize_bytes_to_base64]
