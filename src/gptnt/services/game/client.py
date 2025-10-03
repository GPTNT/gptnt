from dataclasses import dataclass

import anyio
import logfire
import structlog

from gptnt.common.base_client import BaseClient
from gptnt.experiments.time_limits import SECONDS_PER_ACTION
from gptnt.ktane.actions import KtaneAction
from gptnt.ktane.client import RawObservationFrames
from gptnt.ktane.mission_spec import KtaneMissionSpec
from gptnt.ktane.state.bomb import BombState
from gptnt.ktane.state.game import GameState
from gptnt.services.timeouts import ServiceTimeouts

logger = structlog.get_logger()
service_timeouts = ServiceTimeouts()


@dataclass(kw_only=True)
class GameClient(BaseClient):
    """Send game operations."""

    @logfire.instrument("Configure game")
    async def configure_game(self, *, spec: KtaneMissionSpec) -> None:
        """Configure the game with the given event."""
        response = await self.client.post(
            "/configure-experiment", json=spec.model_dump(mode="json")
        )
        logger.debug("Configured game", spec=spec, response=response)
        _ = response.raise_for_status()

    async def get_game_state(self) -> GameState:
        """Get the current game state (blocking)."""
        response = await self.client.get("/state")
        _ = response.raise_for_status()
        return GameState(response.json())

    async def stop_game(self) -> None:
        """Stop the game."""
        response = await self.client.post("/stop-experiment")
        _ = response.raise_for_status()

    async def pause_game(self) -> None:
        """Pause the game."""
        response = await self.client.post("/pause")
        _ = response.raise_for_status()

    async def unpause_game(self) -> None:
        """Unpause the game."""
        response = await self.client.post("/unpause")
        _ = response.raise_for_status()

    async def go_to_main_menu(self) -> None:
        """Reset the game to main menu scene."""
        response = await self.client.post("/reset")
        _ = response.raise_for_status()

    @logfire.instrument("Advance game time")
    async def advance_game_time(self) -> None:
        """Advance the game time by one step."""
        response = await self.client.post("/advance-time")
        _ = response.raise_for_status()
        await anyio.sleep(SECONDS_PER_ACTION)

    @logfire.instrument("Send action")
    async def send_action(self, *, action: KtaneAction) -> None:
        """Send an action to the game."""
        response = await self.client.post("/send-action", json=action.model_dump(mode="json"))

        # Specifically catch the case where the game is over and we are trying to send an action
        if response.is_error and response.headers["X-Reason"] in (
            "Cannot send action to the game in Transitioning state",
            "Cannot send action to the game in PostGame state",
        ):
            logger.warning(
                "Action failed because the game is over. Not raising an error.",
                action=action,
                response=response,
                reason=response.headers["X-Reason"],
            )
        else:
            _ = response.raise_for_status()

    @logfire.instrument("Get bomb state")
    async def get_bomb_state(self) -> BombState:
        """Get the current bomb state (blocking)."""
        response = await self.client.get("/bomb-state")
        _ = response.raise_for_status()

        return BombState.model_validate_json(response.content)

    @logfire.instrument("Get frames")
    async def get_frames(self) -> RawObservationFrames:
        """Get the current frames (blocking)."""
        response = await self.client.get("/observation-frames")
        _ = response.raise_for_status()
        return RawObservationFrames.model_validate_json(response.content)

    @logfire.instrument("Get observation")
    async def get_observation(self) -> tuple[BombState, RawObservationFrames]:
        """Get the current observation (blocking)."""
        frames = await self.get_frames()
        bomb_state = await self.get_bomb_state()
        return bomb_state, frames
