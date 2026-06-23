from enum import Enum
from typing import override


class GameState(Enum):
    """State that the game is in."""

    unknown = ""
    """The game process is still starting."""

    main_menu = "Setup"
    """The game is sitting in the main menu (table scene)."""

    transitioning = "Transitioning"
    """The game is in a loading screen."""

    lights_off = "LightsOff"
    """The game is in a mission, with the lights off."""

    lights_on = "LightsOn"
    """The game is in a mission, with the lights on."""

    game_ended = "PostGame"
    """The game is on the mission finished screen."""

    unlock = "Unlock"

    quitting = "Quitting"

    @override
    @classmethod
    def _missing_(cls, value: object) -> "GameState":  # noqa: WPS110, WPS120
        return cls.unknown
