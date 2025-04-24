import httpx
from structlog import get_logger

from gptnt.api.base_client import BaseClient
from gptnt.api.structures import RoomManagerAPIInfo

_logger = get_logger()


class PlayerClient(BaseClient):
    """API for externally interacting with the PlayerAPI."""

    async def join_room(self, room: RoomManagerAPIInfo) -> None:
        """Makes player join the passed RoomManager's dialogue space."""
        response = await self.client.post(url="/join-room", json=room.model_dump(mode="json"))
        _ = response.raise_for_status()

    # TODO: we need to send the experiment spec to the player for wandb
    async def start_experiment(self) -> bool:
        """Command the player to perform any pre-experiment setup or logging needed."""
        try:
            _ = (await self.client.post(url="/start-experiment")).raise_for_status()
        except httpx.HTTPError:
            _logger.exception("Could not start experiment")
            return False
        return True

    # TODO: rename this to be clearer as to what we are starting it doing
    async def run_for_game(self) -> bool:
        """Command the player to start making actions and messaging in the dialogue space."""
        try:
            _ = (await self.client.post(url="/run-for-game")).raise_for_status()
        except httpx.HTTPError:
            _logger.exception("Could not start game")
            return False
        return True

    # TODO: rename this to be clearer as to what we are starting it doing
    async def run_for_turn(self) -> bool:
        """Command the player to make a single action."""
        try:
            _ = (await self.client.post(url="/run-for-turn")).raise_for_status()
        except httpx.HTTPError:
            _logger.exception("Could not command to take single step")
            return False
        return True

    async def stop_experiment(self) -> bool:
        """Command the player to stop performing actions and using the dialogue space.

        This also signals experiment logging and returning to lobby.
        """
        try:
            _ = (await self.client.post(url="/stop-experiment")).raise_for_status()
        except httpx.HTTPError:
            _logger.exception("Could not stop experiment")
            return False
        return True
