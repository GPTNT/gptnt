from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

import anyio
import httpx
import logfire
import structlog
from faststream.redis import RedisBroker
from pydantic import UUID4, RedisDsn

from gptnt.experiments.time_limits import SECONDS_PER_ACTION
from gptnt.ktane.actions import KtaneAction
from gptnt.ktane.client import RawObservationFrames
from gptnt.ktane.mission_spec import KtaneMissionSpec
from gptnt.ktane.state.bomb import BombState
from gptnt.ktane.state.game import GameState
from gptnt.services.broker import create_redis_broker
from gptnt.services.game.controller import GameCommand
from gptnt.services.timeouts import ServiceTimeouts

logger = structlog.get_logger()
timeouts = ServiceTimeouts()


@dataclass(kw_only=True)
class GameClient:
    """Send game operations."""

    redis_url: RedisDsn = field(default=RedisDsn("redis://localhost:6379/0"))
    _broker: RedisBroker = field(init=False, repr=False)
    _is_started: bool = field(default=False, init=False)

    # Channel names - configurable per game instance
    game_uuid: UUID4 | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        """Initialize FastStream Redis broker for RPC."""
        self._broker = create_redis_broker(self.redis_url)

    @property
    def command_channel(self) -> str:
        """Get the command channel for this game."""
        if not self.game_uuid:
            raise ValueError("Game client not configured with game_id")
        return f"game:{self.game_uuid}:commands"

    @asynccontextmanager
    async def lifespan(self) -> AsyncGenerator[None]:
        """Lifespan manager for the Redis broker."""
        await self.start()
        try:
            yield
        finally:
            await self.close()

    async def start(self) -> None:
        """Start the Redis broker."""
        if not self._is_started:
            await self._broker.start()
            self._is_started = True
            logger.debug("Started Redis game client broker")

    async def close(self) -> None:
        """Close the Redis broker."""
        if self._is_started:
            await self._broker.close()
            self._is_started = False
            logger.debug("Closed Redis game client broker")

    @logfire.instrument("Configure game")
    async def configure_game(self, *, spec: KtaneMissionSpec) -> None:
        """Configure the game with the given spec."""
        channel = self._get_channel("configure_game")
        response = await self._broker.request(spec.model_dump(mode="json"), channel=channel)
        _ = await response.decode()
        logger.debug("Configured game", spec=spec)

    async def get_game_state(self) -> GameState:
        """Get the current game state."""
        channel = self._get_channel("get_game_state")
        response = await self._broker.request({}, channel=channel)

        state_value = await response.decode()
        return GameState(state_value)

    async def stop_game(self) -> None:
        """Stop the game."""
        logger.debug("Stopping the game")
        channel = self._get_channel("stop_game")
        response = await self._broker.request(
            {}, channel=channel, timeout=timeouts.game_request_timeout
        )
        _ = await response.decode()

    async def pause_game(self) -> None:
        """Pause the game."""
        channel = self._get_channel("pause_game")
        response = await self._broker.request({}, channel=channel)
        _ = await response.decode()

    async def unpause_game(self) -> None:
        """Unpause the game."""
        channel = self._get_channel("unpause_game")
        response = await self._broker.request({}, channel=channel)
        _ = await response.decode()

    async def go_to_main_menu(self) -> None:
        """Reset the game to main menu scene."""
        channel = self._get_channel("go_to_main_menu")
        response = await self._broker.request({}, channel=channel)
        _ = await response.decode()

    @logfire.instrument("Advance game time")
    async def advance_game_time(self) -> None:
        """Advance the game time by one step."""
        channel = self._get_channel("advance_game_time")
        response = await self._broker.request({}, channel=channel)
        _ = await response.decode()

        await anyio.sleep(SECONDS_PER_ACTION)

    @logfire.instrument("Send action")
    async def send_action(self, *, action: KtaneAction) -> None:
        """Send an action to the game."""
        channel = self._get_channel("send_action")

        response = await self._broker.request(action.model_dump(mode="json"), channel=channel)
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
        response = await self._broker.request(
            {}, channel=channel, timeout=timeouts.get_bomb_state_timeout
        )

        # Response body is bytes, decode and parse
        bomb_state_json = await response.decode()
        return BombState.model_validate(bomb_state_json)

    @logfire.instrument("Get frames")
    async def get_frames(self) -> RawObservationFrames:
        """Get the current frames."""
        channel = self._get_channel("get_frames")
        response = await self._broker.request(
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
