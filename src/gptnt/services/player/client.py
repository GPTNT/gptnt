from dataclasses import dataclass

import logfire
import structlog
from httpx import Response

from gptnt.common.base_client import BaseClient
from gptnt.ktane.state.bomb import BombState
from gptnt.players.prompts.reflection import ReflectionMessage
from gptnt.players.specification import PlayerProtocol
from gptnt.services.events.player import PlayerMessage, StopPlayerEvent
from gptnt.services.experiment_descriptor import ExperimentDescriptor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class PlayerClient(BaseClient):
    """Interact with the player."""

    async def send_message(self, message: str) -> Response:
        """Send a message to the player."""
        response = await self.client.post(
            "/send-message", json=PlayerMessage(message=message).model_dump(mode="json")
        )
        _ = response.raise_for_status()
        return response

    async def send_feedback(self, feedback: str) -> Response:
        """Send feedback to the player."""
        response = await self.client.post(
            "/send-feedback", json=PlayerMessage(message=feedback).model_dump(mode="json")
        )
        _ = response.raise_for_status()
        return response

    @logfire.instrument("Configure player")
    async def configure_player(
        self, *, player_protocol: PlayerProtocol, experiment_descriptor: ExperimentDescriptor
    ) -> Response:
        """Configure the player with the given protocol."""
        response = await self.client.post(
            "/configure-for-experiment",
            json={
                "protocol": player_protocol.model_dump(mode="json"),
                "experiment_descriptor": experiment_descriptor.model_dump(mode="json"),
            },
        )
        _ = response.raise_for_status()
        return response

    async def forward_pass(self) -> Response:
        """Tell a player to perform a forward pass."""
        response = await self.client.post("/forward")
        _ = response.raise_for_status()
        return response

    async def reset_player(self) -> Response:
        """Reset the player to its initial state."""
        response = await self.client.post("/reset")
        _ = response.raise_for_status()
        return response

    async def send_reflection_request(self, reflection_message: ReflectionMessage) -> Response:
        """Ask the player to perform a reflection."""
        try:
            response = await self.client.post(
                "/reflection",
                json=PlayerMessage(message=reflection_message).model_dump(mode="json"),
            )
        except TimeoutError:
            logger.exception(
                "TimeoutError when sending reflection request. BUT we don't care about it and the expeirment is not being forced to stop so we continue on, but it might be a sign that the AI is down or something. "
            )
            return Response(503)

        if response.is_error:
            logger.exception(
                "Error with reflection request, but we continue on. We don't want a failed reflection to stop the experiment."
            )
        return response

    async def stop_player(
        self, *, bomb_state: BombState | None = None, is_hard_crash: bool = False
    ) -> Response:
        """Stop the player and end the experiment."""
        response = await self.client.post(
            "/stop",
            json=StopPlayerEvent(bomb_state=bomb_state, hard_crash=is_hard_crash).model_dump(
                mode="json"
            ),
        )
        _ = response.raise_for_status()
        return response
