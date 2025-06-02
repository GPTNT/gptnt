from dataclasses import dataclass
from typing import Any

from pydantic.types import UUID4


class ExceptionUnhandledError(Exception):
    """Exceptions in a background task not handled by the child class."""


class EMConnectionFailedError(Exception):
    """Error representing failure to connect with the EM."""


class EMConnectionClosedError(Exception):
    """Error representing the EM connection being closed."""


class ConfigurationFailedError(Exception):
    """Error representing the failure to configure the room subservices."""


class PlayerTookTooLongError(Exception):
    """Error representing a player taking too long to take an action."""


class GameTooLongError(Exception):
    """Error representing a game taking too long.

    May wish to remove this error in the future.
    """


class GameProcessDiedError(Exception):
    """Exception indicating the game process has died."""


@dataclass(kw_only=True)
class HeartbeatWatchdogTriggeredError(Exception):
    """Error representing a failed heartbeat watchdog."""

    uuid: UUID4
    metadata: dict[str, Any]
