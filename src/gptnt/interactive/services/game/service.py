from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Literal, override

import httpx
import structlog
from fastapi import HTTPException
from faststream.redis import RedisBroker

from gptnt.interactive.services.game.context import GameServiceContext
from gptnt.interactive.services.heartbeat.base import ReadyState
from gptnt.interactive.services.rpc import BaseRPCService
from gptnt.ktane.actions import KtaneGameplayInput
from gptnt.ktane.client import FrameBuffer
from gptnt.ktane.mission_spec import KtaneMissionConfig
from gptnt.ktane.state.bomb import BombState
from gptnt.ktane.state.game import GameState
from gptnt.observability.span_timing import set_timing_identity

logger = structlog.get_logger()

GameCommand = Literal[
    "advance_game_time",
    "configure_game",
    "get_bomb_state",
    "get_frames",
    "get_game_state",
    "go_to_main_menu",
    "pause_game",
    "send_action",
    "set_game_speed",
    "stop_game",
    "unpause_game",
]


@dataclass(kw_only=True)
class GameService(GameServiceContext, BaseRPCService[GameCommand]):
    """Handle game commands from Redis RPC requests.

    Registers Redis RPC handlers and coordinates the game lifecycle while delegating the underlying
    work to the core game components managed by GameServiceContext.
    """

    broker: RedisBroker

    def __post_init__(self) -> None:
        """Initialize the command handler."""
        # Initialise the GameServiceContext
        super().__post_init__()

        self.commands = {
            "advance_game_time": self.advance_time,
            "configure_game": self.configure_game,
            "get_bomb_state": self.get_bomb_state,
            "get_frames": self.get_observation_frames,
            "get_game_state": self.get_game_state,
            "go_to_main_menu": self.reset_game,
            "pause_game": self.pause_game,
            "send_action": self.send_action,
            "set_game_speed": self.set_game_speed,
            "stop_game": self.stop_game,
            "unpause_game": self.unpause_game,
        }
        self.register_subscribers()

    @property
    @override
    def command_channel(self) -> str:
        """Get the command channel for this game."""
        return f"game:{self.uuid}:commands"

    @override
    @asynccontextmanager
    async def lifespan(self) -> AsyncGenerator[None]:
        """Lifespan for the Game Instance."""
        async with self.broker, super().lifespan():
            yield

    async def get_game_state(self) -> GameState:
        """Get the current game state."""
        return self.state_monitor.state.value

    async def configure_game(self, config: KtaneMissionConfig) -> bool:
        """Configure a new experiment."""
        # The game process does not know the experiment session_id; tag span rows with the
        # game_uuid so they can be joined to a session via the experiment records at query time.
        set_timing_identity(game_uuid=str(self.uuid), player_role="game")

        if self.state_monitor.state.value != GameState.main_menu:
            raise HTTPException(
                status_code=400,
                detail="Game is not in setup state, cannot configure experiment. Try to reset the game first.",
                headers={
                    "X-Reason": f"Invalid game state for creating a new experiment. Expected 'Setup', got '{self.state_monitor.state.value}'"
                },
            )

        try:
            _ = await self.ktane_client.start_mission(config)
        except httpx.HTTPStatusError as err:
            logger.exception(
                "Failed to start mission",
                config=config,
                reason=err.response.text,
                request=err.response.request,
                state_history=self.state_monitor.history,
                light_on_event=self.state_monitor.first_lights_on.is_set(),
            )
            raise HTTPException(
                status_code=503,
                detail="Failed to start the mission",
                headers={"X-Reason": err.response.text},  # noqa: WPS204
            ) from err

        _ = await self.state_monitor.first_lights_off.wait()
        return await self.ktane_client.stop_time()

    async def stop_game(self) -> bool:
        """Stop the current experiment.

        If we are not ready, it means the game has already been rebooted and should not be rebooted
        again otherwise it will just hang forever. Therefore only terminate the process if we are
        in the ready state. If we are not ready, the GameServiceContext will take care of it.
        """
        logger.debug("Stopping game via controller")
        if self.ready_state == ReadyState.ready:
            self.expected_death.set()
            await self.process_manager.terminate()

        return True

    async def pause_game(self) -> bool:
        """Pause the game."""
        try:
            return await self.ktane_client.stop_time()
        except httpx.HTTPStatusError as err:
            logger.exception(
                "Failed to pause the game", reason=err.response.text, request=err.response.request
            )
            raise HTTPException(
                status_code=503,
                detail="Failed to pause the game",
                headers={"X-Reason": err.response.text},
            ) from err

    async def unpause_game(self) -> bool:
        """Unpause the game."""
        try:
            return await self.ktane_client.resume_time()
        except httpx.HTTPStatusError as err:
            logger.exception(
                "Failed to unpause the game",
                reason=err.response.text,
                request=err.response.request,
            )
            raise HTTPException(
                status_code=503,
                detail="Failed to unpause the game",
                headers={"X-Reason": err.response.text},
            ) from err

    async def reset_game(self) -> bool:
        """Reset the game to main menu."""
        try:
            return await self.ktane_client.go_to_main_menu()
        except httpx.HTTPStatusError as err:
            logger.exception(
                "Failed to reset the game", reason=err.response.text, request=err.response.request
            )
            raise HTTPException(
                status_code=503,
                detail="Failed to reset the game",
                headers={"X-Reason": err.response.text},
            ) from err

    async def advance_time(self) -> bool:
        """Advance the game time."""
        try:
            return await self.ktane_client.advance_time()
        except httpx.HTTPStatusError as err:
            logger.exception(
                "Failed to advance game time",
                reason=err.response.text,
                request=err.response.request,
            )
            raise HTTPException(
                status_code=503,
                detail="Failed to advance game time",
                headers={"X-Reason": err.response.text},
            ) from err

    async def set_game_speed(self, speed: float | None = None) -> bool:
        """Set the game speed."""
        try:
            return await self.ktane_client.set_game_speed(speed=speed)
        except httpx.HTTPStatusError as err:
            logger.exception(
                "Failed to set game speed", reason=err.response.text, request=err.response.request
            )
            raise HTTPException(
                status_code=503,
                detail="Failed to set game speed",
                headers={"X-Reason": err.response.text},
            ) from err

    async def send_action(self, action: KtaneGameplayInput) -> bool:
        """Send an action to the game."""
        try:
            return await self.ktane_client.send_action(action)
        except httpx.HTTPStatusError as err:
            logger.exception("Failed to send action", action=action, reason=err.response.text)
            raise HTTPException(
                status_code=503,
                detail="Failed to send action",
                headers={"X-Reason": err.response.text},
            ) from err

    async def get_bomb_state(self) -> BombState:
        """Get the current bomb state."""
        try:
            return await self.ktane_client.get_bomb_state()
        except httpx.RequestError as request_err:
            raise HTTPException(
                status_code=503, detail="Failed to REQUEST bomb state"
            ) from request_err
        except httpx.HTTPStatusError as err:
            raise HTTPException(
                status_code=503,
                detail="Failed to RECEIVE bomb state",
                headers={"X-Reason": err.response.text},
            ) from err

    async def get_observation_frames(self) -> FrameBuffer:
        """Get the current observation frames."""
        try:
            return await self.ktane_client.get_observation_frames()
        except httpx.RequestError as request_err:
            raise HTTPException(
                status_code=503, detail="Failed to REQUEST observation frames"
            ) from request_err
        except httpx.HTTPStatusError as err:
            raise HTTPException(
                status_code=503,
                detail="Failed to RECEIVE observation frames",
                headers={"X-Reason": err.response.text},
            ) from err
