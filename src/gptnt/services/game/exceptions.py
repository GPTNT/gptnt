class GameServiceError(Exception):
    """Base class for all game service-related exceptions."""


class GameIsOverError(GameServiceError):
    """Raised when the game is over and no further actions can be taken."""


class CannotGetObservationError(GameServiceError):
    """Raised when the bomb state/observation cannot be retrieved."""
