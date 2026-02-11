from dataclasses import dataclass, field

import anyio
import httpx
import logfire
import structlog
from faststream.redis import RedisBroker
from pydantic import UUID4

from gptnt.experiments.time_limits import SECONDS_PER_ACTION
from gptnt.ktane.actions import KtaneGameplayInput
from gptnt.ktane.client import RawObservationFrames
from gptnt.ktane.mission_spec import KtaneMissionConfig, KtaneMissionSpec
from gptnt.ktane.state.bomb import BombState
from gptnt.ktane.state.game import GameState
from gptnt.services.game.controller import GameCommand
from gptnt.services.timeouts import ServiceTimeouts

logger = structlog.get_logger()
timeouts = ServiceTimeouts()


@dataclass(kw_only=True)
class GameClient:
    """Send game operations."""

    broker: RedisBroker

    # Channel names - configurable per game instance
    game_uuid: UUID4 | None = field(default=None, init=False)

    @property
    def command_channel(self) -> str:
        """Get the command channel for this game."""
        if not self.game_uuid:
            raise ValueError("Game client not configured with game_id")
        return f"game:{self.game_uuid}:commands"

    @logfire.instrument("Configure game")
    async def configure_game(self, *, spec: KtaneMissionSpec, session_id: UUID4) -> None:
        """Configure the game with the given spec."""
        channel = self._get_channel("configure_game")
        configure_message = KtaneMissionConfig(**spec.model_dump(), session_id=session_id)
        response = await self.broker.request(
            message=configure_message.model_dump(mode="json"), channel=channel
        )
        _ = await response.decode()
        logger.debug("Configured game", spec=spec, session_id=session_id)

    async def get_game_state(self) -> GameState:
        """Get the current game state."""
        channel = self._get_channel("get_game_state")
        response = await self.broker.request({}, channel=channel)

        state_value = await response.decode()
        return GameState(state_value)

    async def stop_game(self) -> None:
        """Stop the game."""
        logger.debug("Stopping the game")
        channel = self._get_channel("stop_game")
        response = await self.broker.request(
            {}, channel=channel, timeout=timeouts.game_request_timeout
        )
        _ = await response.decode()

    async def pause_game(self) -> None:
        """Pause the game."""
        channel = self._get_channel("pause_game")
        response = await self.broker.request({}, channel=channel)
        _ = await response.decode()

    async def unpause_game(self) -> None:
        """Unpause the game."""
        channel = self._get_channel("unpause_game")
        response = await self.broker.request({}, channel=channel)
        _ = await response.decode()

    async def go_to_main_menu(self) -> None:
        """Reset the game to main menu scene."""
        channel = self._get_channel("go_to_main_menu")
        response = await self.broker.request({}, channel=channel)
        _ = await response.decode()

    @logfire.instrument("Advance game time")
    async def advance_game_time(self) -> None:
        """Advance the game time by one step."""
        channel = self._get_channel("advance_game_time")
        response = await self.broker.request({}, channel=channel)
        _ = await response.decode()

        await anyio.sleep(SECONDS_PER_ACTION)

    @logfire.instrument("Send action")
    async def send_action(self, *, action: KtaneGameplayInput) -> None:
        """Send an action to the game."""
        channel = self._get_channel("send_action")

        response = await self.broker.request(action.model_dump(mode="json"), channel=channel)
        try:
            _ = await response.decode()
        except httpx.HTTPStatusError as exc:
            # Special case: game over is expected in some scenarios, don't propagate
            # Check X-Reason header (preserved from FastAPI HTTPException)
            x_reason = exc.response.headers.get("X-Reason")
            if x_reason in (
                "Cannot send action to the game in Transitioning state",
                "Cannot send action to the game in PostGame state",
            ):
                logger.warning(
                    "Action failed because the game is over. Not raising an error.",
                    action=action,
                    reason=x_reason,
                )
            else:
                raise

    @logfire.instrument("Get bomb state")
    async def get_bomb_state(self) -> BombState:
        """Get the current bomb state."""
        channel = self._get_channel("get_bomb_state")
        response = await self.broker.request(
            {}, channel=channel, timeout=timeouts.get_bomb_state_timeout
        )

        # Response body is bytes, decode and parse
        bomb_state_json = await response.decode()
        return BombState.model_validate(bomb_state_json)

    @logfire.instrument("Get frames")
    async def get_frames(self) -> RawObservationFrames:
        """Get the current frames."""
        channel = self._get_channel("get_frames")
        response = await self.broker.request(
            {}, channel=channel, timeout=timeouts.get_observation_timeout
        )

        frames_json = await response.decode()
        return RawObservationFrames.model_validate(frames_json)

    @logfire.instrument("Get observation")
    async def get_observation(self) -> tuple[BombState, RawObservationFrames]:
        """Get the current observation."""
        frames = await self.get_frames()
        bomb_state = await self.get_bomb_state()
        return bomb_state, frames

    def _get_channel(self, command: GameCommand) -> str:
        """Get the full Redis channel name for a given command."""
        return f"{self.command_channel}:{command}"
