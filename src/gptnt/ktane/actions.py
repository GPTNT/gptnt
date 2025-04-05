from enum import Enum
from typing import Annotated, Self

import annotated_types
from pydantic import BaseModel, model_validator


class GameActionType(Enum):
    """Actions that can be performed in the game."""

    turn_left = "turn_left"
    """Only 90deg rotations are allowed."""

    turn_right = "turn_right"
    """Only 90deg rotations are allowed."""

    turn_around = "turn_around"
    """Rotate the bomb 180 degrees."""

    roll_up = "roll_up"
    """Roll the bomb up 90 degrees."""

    roll_down = "roll_down"
    """Roll the bomb down 90 degrees."""

    zoom_out = "zoom_out"
    """Zoom out of the current depth (i.e. right-clicking)."""

    click = "click"
    """Click (and immediate release) on a point."""

    hold = "hold"
    """Hold (and do not release) on a point."""

    release = "release"
    """Release the hold (does not use a location)."""

    @classmethod
    def require_location(cls) -> "set[GameActionType]":
        """Return the set of actions that require a location to interact on."""
        return {cls.click, cls.hold}


class RelativeCoordinate(BaseModel):
    """Coordinates for location-based actions.

    The top-left of the screen is (0, 0) and the bottom-right is (1, 1).
    """

    x_pos: Annotated[float, annotated_types.Ge(0), annotated_types.Le(1)]
    """Relative x-coordinate from the left."""

    y_pos: Annotated[float, annotated_types.Ge(0), annotated_types.Le(1)]
    """Relative y-coordinate from the top."""


class KtaneBaseAction[LocationDataT](BaseModel):
    """Interaction action for the player to take in the game."""

    action: GameActionType
    location: LocationDataT | None = None
    """Location to interact with, if needed."""

    @model_validator(mode="after")
    def check_actions_align_with_location_use(self) -> Self:
        """Only certain actions require a location, so we make sure there's not mismatch."""
        # Err if action requires location but no location is provided
        if self.action in GameActionType.require_location() and self.location is None:
            raise ValueError(f"Action {self.action} requires a location but none was provided.")

        # Err if action does not require location but location is provided
        if self.action not in GameActionType.require_location() and self.location is not None:
            raise ValueError(
                f"Action {self.action} does not require a location but one was provided."
            )

        return self


KtaneAction = KtaneBaseAction[RelativeCoordinate]
