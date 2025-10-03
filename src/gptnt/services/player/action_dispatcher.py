from dataclasses import dataclass, field
from typing import Any, override

import logfire
import structlog

from gptnt.ktane.actions import KtaneBaseAction, RelativeCoordinate
from gptnt.players.action_dispatcher import BaseActionDispatcher
from gptnt.players.specification import PlayerProtocol
from gptnt.services.experiment_descriptor import ExperimentDescriptor
from gptnt.services.game.client import GameClient
from gptnt.services.player.message_handler import MessageManager

logger = structlog.get_logger()


@dataclass(kw_only=True)
class ActionDispatcher(BaseActionDispatcher):
    """Dispatch actions from the agent over the messaging queues."""

    game_client: GameClient
    message_manager: MessageManager

    experiment_descriptor: ExperimentDescriptor = field(init=False, repr=False)

    @override
    def configure_for_experiment(
        self,
        *,
        protocol: PlayerProtocol,
        experiment_descriptor: ExperimentDescriptor,
        **kwargs: Any,
    ) -> None:
        super().configure_for_experiment(protocol=protocol)
        self.experiment_descriptor = experiment_descriptor

    @override
    @logfire.instrument("Send dialogue message")
    async def send_dialogue_message(self, message: str) -> None:
        """Send the dialogue message to the other player(s)."""
        await self.message_manager.send_message(message=message)
        logger.debug("Sent dialogue message", message=message, current_role=self.protocol.role)

    @override
    async def send_game_action(self, action: KtaneBaseAction[RelativeCoordinate]) -> None:
        """Send a game action to the current game."""
        await self.game_client.send_action(action=action)
        logger.debug(
            "Sent action to game",
            action=action,
            current_role=self.protocol.role,
            game_uuid=self.experiment_descriptor.game_uuid,
        )
