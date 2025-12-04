from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

import httpx
import structlog
from fastapi import HTTPException
from faststream.redis import RedisBroker

from gptnt.ktane.actions import KtaneGameplayInput
from gptnt.ktane.client import RawObservationFrames
from gptnt.ktane.mission_spec import KtaneMissionSpec
from gptnt.ktane.state.bomb import BombState
from gptnt.ktane.state.game import GameState
from gptnt.services.events.heartbeat import ReadyState
from gptnt.services.game.supervisor import GameSupervisor

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

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
class GameController(GameSupervisor):
    """Handle game commands from Redis RPC requests."""

    broker: RedisBroker

    def __post_init__(self) -> None:
        """Initialize the command handler."""
        super().__post_init__()
        self.commands: dict[GameCommand, Callable[..., Awaitable[Any]]] = {
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
    def command_channel(self) -> str:
        """Get the command channel for this game."""
        return f"game:{self.uuid}:commands"

    def register_subscribers(self) -> None:
        """Register all the command subscribers with the broker."""
        for command_name, command_func in self.commands.items():
            channel_name = f"{self.command_channel}:{command_name}"
            logger.info("Registering command", channel_name=channel_name, command=command_name)
            _ = self.broker.subscriber(channel_name)(command_func)

    async def get_game_state(self) -> GameState:
        """Get the current game state."""
        return self.state_monitor.state.value

    async def configure_game(self, spec: KtaneMissionSpec) -> bool:
        """Configure a new experiment."""
        if self.state_monitor.state.value != GameState.main_menu:
            raise HTTPException(
                status_code=400,
                detail="Game is not in setup state, cannot configure experiment. Try to reset the game first.",
                headers={
                    "X-Reason": f"Invalid game state for creating a new experiment. Expected 'Setup', got '{self.state_monitor.state.value}'"
                },
            )

        try:
            _ = await self.ktane_client.start_mission(spec)
        except httpx.HTTPStatusError as err:
            logger.exception(
                "Failed to start mission",
                spec=spec,
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
        in the ready state. If we are not ready, the GameSupervisor will take care of it.
        """
        logger.debug("Stopping game via controller")
        if self.ready_state == ReadyState.ready:
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

    async def get_observation_frames(self) -> RawObservationFrames:
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
