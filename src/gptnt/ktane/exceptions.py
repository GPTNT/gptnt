import httpx


class UnhealthyGameError(Exception):
    """Exception raised when something is wrong with the game."""


class GameServerError(UnhealthyGameError):
    """Exception when there is something wrong with the game server."""

    def __init__(self, *, message: str, response: httpx.Response) -> None:
        super().__init__()
        self.message = message
        self.response = response
        self.request = response.request
        self.reason = response.text
