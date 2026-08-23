from typing import Annotated, Literal, TypeVar

from annotated_types import MaxLen, Predicate
from pydantic import AfterValidator, BaseModel, NonNegativeInt

from gptnt.ktane.actions import RelativeCoordinate


class PixelLocation(BaseModel):
    """Absolute pixel coordinate to interact with in the game."""

    x: NonNegativeInt  # noqa: WPS111
    """Absolute x-coordinate from the left."""

    y: NonNegativeInt  # noqa: WPS111
    """Absolute y-coordinate from the top."""


class ScaledLocation(BaseModel):
    """Normalised coordinate to interact with in the game."""

    x: NonNegativeInt  # noqa: WPS111
    """Normalised x-coordinate from the left."""

    y: NonNegativeInt  # noqa: WPS111
    """Normalised y-coordinate from the top."""


type SingleAlphabetLetter = Annotated[
    str, MaxLen(1), Predicate(str.isalpha), AfterValidator(lambda letter: letter.upper())
]

type SetOfMarksLocation = NonNegativeInt | SingleAlphabetLetter
"""Set of marks location to interact with; must be an int >= 0, or one letter A-Z."""

type InteractableLocation = (
    RelativeCoordinate | SetOfMarksLocation | PixelLocation | ScaledLocation
)
"""Location-methods to interact with in the game."""

LocationDataT_co = TypeVar("LocationDataT_co", bound=InteractableLocation, covariant=True)

type InteractionLocationMethod = Literal["set-of-marks", "coordinates"]
"""Whether interaction locations are predicted as set-of-marks or coordinates."""

type CoordinateMode = Literal["absolute", "normalised"]
"""The flavour of coordinates that the model supports.

The normalised scale is configured by `PlayerCapabilities.coordinate_scale`; absolute
coordinates are pixel values based on the image dimensions.
"""
