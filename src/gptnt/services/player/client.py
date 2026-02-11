from dataclasses import dataclass
from typing import Any

import httpx
import logfire
import structlog
from faststream.redis import RedisBroker
from pydantic import UUID4

from gptnt.ktane.state.bomb import BombState
from gptnt.players.specification import PlayerProtocol
from gptnt.services.events.player import PlayerMessage, StopPlayerEvent
from gptnt.services.experiment_descriptor import ExperimentDescriptor
from gptnt.services.player.controller import PlayerCommand
from gptnt.services.timeouts import ServiceTimeouts

logger = structlog.get_logger()

timeouts = ServiceTimeouts()


@dataclass(kw_only=True)
class PlayerClient:
    """Client to interact with player service via Redis RPC."""

    player_uuid: UUID4
    redis_broker: RedisBroker

    @property
    def command_channel(self) -> str:
        """Get the command channel for this player."""
        return f"player:{self.player_uuid}:commands"

    async def get_state(self) -> str:
        """Get player state."""
        return await self._send_command("get_state")

    @logfire.instrument("Send feedback")
    async def send_feedback(self, feedback: str) -> bool:
        """Send feedback to the player."""
        return await self._send_command("send_feedback", {"message": feedback})

    @logfire.instrument("Configure player ({player_protocol.role})")
    async def configure_player(
        self, *, player_protocol: PlayerProtocol, experiment_descriptor: ExperimentDescriptor
    ) -> bool:
        """Configure the player with the given protocol."""
        payload = {
            "protocol": player_protocol.model_dump(mode="json"),
            "experiment_descriptor": experiment_descriptor.model_dump(mode="json"),
        }
        return await self._send_command("configure_for_experiment", payload)

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
        """Send a command via Redis RPC and wait for response.

        Note: The broker is already started and managed by FastStream.
        """
        channel = f"{self.command_channel}:{command}"
        response = await self.redis_broker.request(
            payload or {}, channel=channel, timeout=timeouts.redis_rpc_timeout
        )
        return await response.decode()
