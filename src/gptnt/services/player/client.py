from dataclasses import dataclass, field
from typing import Any

import httpx
import logfire
import structlog
from faststream.redis import RedisBroker
from pydantic import UUID4, RedisDsn

from gptnt.ktane.state.bomb import BombState
from gptnt.players.specification import PlayerProtocol
from gptnt.services.broker import create_redis_broker
from gptnt.services.events.player import PlayerMessage, StopPlayerEvent
from gptnt.services.experiment_descriptor import ExperimentDescriptor
from gptnt.services.player.controller import PlayerCommand

logger = structlog.get_logger()


@dataclass(kw_only=True)
class PlayerClient:
    """Client to interact with player service via Redis RPC."""

    player_uuid: UUID4
    redis_url: RedisDsn = field(default=RedisDsn("redis://localhost:6379/0"))
    _broker: RedisBroker = field(init=False, repr=False)
    _is_started: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        """Initialize FastStream Redis broker for RPC."""
        self._broker = create_redis_broker(self.redis_url)

    @property
    def command_channel(self) -> str:
        """Get the command channel for this player."""
        return f"player:{self.player_uuid}:commands"

    async def start(self) -> None:
        """Start the Redis broker."""
        if not self._is_started:
            await self._broker.start()
            self._is_started = True
            logger.debug("Started Redis player client", player_uuid=self.player_uuid)

    async def close(self) -> None:
        """Close the Redis broker."""
        if self._is_started:
            await self._broker.close()
            self._is_started = False
            logger.debug("Closed Redis player client")

    async def get_state(self) -> str:
        """Get player state."""
        return await self._send_command("get_state")

    @logfire.instrument("Send feedback")
    async def send_feedback(self, feedback: str) -> bool:
        """Send feedback to the player."""
        return await self._send_command("send_feedback", {"message": feedback})

    @logfire.instrument("Configure player")
    async def configure_player(
        self, *, player_protocol: PlayerProtocol, experiment_descriptor: ExperimentDescriptor
    ) -> bool:
        """Configure the player with the given protocol."""
        payload = {
            "protocol": player_protocol.model_dump(mode="json"),
            "experiment_descriptor": experiment_descriptor.model_dump(mode="json"),
        }
        return await self._send_command("configure_for_experiment", payload)

    @logfire.instrument("Forward pass")
    async def forward_pass(self) -> dict[str, Any]:
        """Tell a player to perform a forward pass."""
        return await self._send_command("forward_pass")

    async def reset_player(self) -> bool:
        """Reset the player to its initial state."""
        return await self._send_command("reset")

    async def send_reflection_request(self, reflection_message: str) -> bool:
        """Ask the player to perform a reflection."""
        payload = PlayerMessage(message=reflection_message).model_dump(mode="json")
        try:
            response_data = await self._send_command("reflection", payload)
        except TimeoutError:
            logger.exception(
                "TimeoutError when sending reflection request. BUT we don't care about it and the experiment is not being forced to stop so we continue on, but it might be a sign that the AI is down or something."
            )
            return False
        except httpx.HTTPError:
            logger.exception(
                "Error with reflection request, but we continue on. We don't want a failed reflection to stop the experiment."
            )
            return False

        return bool(response_data)

    async def stop_player(
        self, *, bomb_state: BombState | None = None, is_hard_crash: bool = False
    ) -> dict[str, str]:
        """Stop the player and end the experiment."""
        payload = StopPlayerEvent(bomb_state=bomb_state, hard_crash=is_hard_crash).model_dump(
            mode="json"
        )
        return await self._send_command("stop", payload)

    async def _send_command(
        self, command: PlayerCommand, payload: dict[str, Any] | None = None
    ) -> Any:
        """Send a command via Redis RPC and wait for response."""
        if not self._is_started:
            await self.start()

        channel = f"{self.command_channel}:{command}"
        response = await self._broker.request(payload or {}, channel=channel, timeout=600)
        return await response.decode()
