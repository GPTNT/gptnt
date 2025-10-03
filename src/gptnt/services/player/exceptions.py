from httpx import HTTPError


class PlayerHTTPError(HTTPError):
    """Base exception for player-related errors."""


class PlayerRequestError(PlayerHTTPError):
    """Exception raised for HTTP request errors to the player service."""


class PlayerResponseError(PlayerHTTPError):
    """Exception raised for unexpected responses from the player service."""


class PlayerForwardPassFailError(PlayerResponseError):
    """Exception raised when a player fails to perform a forward pass."""
