from contextlib import suppress
from enum import Enum
from typing import Annotated, Any, Literal, Self

import annotated_types
import structlog
from httpx import QueryParams
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

logger = structlog.get_logger()


class GameActionType(Enum):
    """Actions that can be performed in the game."""

    rotate_left = "left"
    """Only 90deg rotations are allowed."""

    rotate_right = "right"
    """Only 90deg rotations are allowed."""

    flip = "flip"
    """Rotate the bomb 180 degrees."""

    roll_up = "up"
    """Roll the bomb up 90 degrees."""

    roll_down = "down"
    """Roll the bomb down 90 degrees."""

    zoom_out = "out"
    """Zoom out of the current depth (i.e. right-clicking)."""

    click_release = "click"
    """Click (and immediate release) on a point."""

    hold = "hold"
    """Hold (and do not release) on a point."""

    release = "release"
    """Release the hold (does not use a location)."""

    @classmethod
    def require_location(cls) -> "set[GameActionType]":
        """Return the set of actions that require a location to interact on."""
        return {cls.click_release, cls.hold}


class RelativeCoordinate(BaseModel):
    """Coordinates for location-based actions.

    The top-left of the screen is (0, 0) and the bottom-right is (1, 1).
    """

    x_pos: Annotated[float, annotated_types.Ge(0), annotated_types.Le(1)]
    """Relative x-coordinate from the left."""

    y_pos: Annotated[float, annotated_types.Ge(0), annotated_types.Le(1)]
    """Relative y-coordinate from the top."""


class KtaneBaseAction[KtaneActionType, LocationDataT](BaseModel):
    """Interaction action for the player to take in the game."""

    model_config = ConfigDict(
        # Replace any unsupported characters for the output type
        model_title_generator=lambda model_type: model_type.__name__.replace("[", "")
        .replace("]", "")
        .strip()
    )

    action: KtaneActionType
    location: LocationDataT | None = None
    """Location to interact with, if needed."""

    @property
    def is_clicking_action(self) -> bool:
        """Check if the action is a clicking action."""
        return self.action in GameActionType.require_location()

    @model_validator(mode="after")
    def check_actions_align_with_location_use(self) -> Self:
        """Only certain actions require a location, so we make sure there's not mismatch."""
        # Err if action requires location but no location is provided
        if self.action in GameActionType.require_location() and self.location is None:
            raise ValueError(f"Action {self.action} requires a location but none was provided.")

        # Err if action does not require location but location is provided
        if self.action not in GameActionType.require_location() and self.location is not None:
            logger.warning(
                f"Action {self.action} does not require a location but one was provided. Ignoring it."
            )
            self.location = None

        return self

    @field_validator("action", mode="before")
    @classmethod
    def try_validate_action_by_name(cls, action: Any) -> GameActionType | Any:
        """Validate the action using the GameActionType enum name."""
        with suppress(KeyError):
            return GameActionType[action]
        return action

    def to_query_params(self) -> QueryParams:
        """Convert the action to query parameters for the API."""
        location = (
            self.location.model_dump(mode="json", exclude_none=True)
            if isinstance(self.location, BaseModel)
            else {}
        )
        return QueryParams(
            {**self.model_dump(mode="json", exclude_unset=True, include={"action"}), **location}
        )


type GameActionTypeWithMagic = GameActionType | Literal["magic"]
type KtaneGameplayInput = KtaneBaseAction[GameActionTypeWithMagic, RelativeCoordinate]
"""Everything the game actually accepts as input for gameplay actions."""
