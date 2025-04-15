from fastapi import APIRouter, FastAPI

from gptnt.players.base_player import BasePlayer


class PlayerAPI:
    """Run the player as an API.

    We wrap a wrapper around a player to run as an FastAPI app so we can update/control things.
    """

    def __init__(self, *, player: BasePlayer) -> None:
        self.app = FastAPI()
        self._router = APIRouter()

        self.player = player
