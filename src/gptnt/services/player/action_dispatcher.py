from dataclasses import dataclass
from typing import Any, override

import logfire
import structlog

from gptnt.ktane.actions import KtaneGameplayInput
from gptnt.players.action_dispatcher import BaseActionDispatcher
from gptnt.players.specification import PlayerProtocol
from gptnt.services.experiment_descriptor import ExperimentDescriptor
from gptnt.services.game.client import GameClient
from gptnt.services.player.message_handler import MessageHandler

logger = structlog.get_logger()


@dataclass(kw_only=True)
class ActionDispatcher(BaseActionDispatcher):
    """Dispatch actions to the other places.

    Now you might be wondering why this class even exists, since it could just be used directly
    through inheritance. Well the main reason is for composition purposes, so that the player
    supervisor is just instantiated with an action dispatcher rather than inheriting from it. This
    means that within this class, we can do whatever we want to set it up and just use it as is
    """

    game_client: GameClient
    message_handler: MessageHandler

    @override
    def configure_for_experiment(
        self,
        *,
        protocol: PlayerProtocol,
        experiment_descriptor: ExperimentDescriptor,
        **kwargs: Any,
    ) -> None:
        """Configure for experiment and set up Redis channels."""
        super().configure_for_experiment(protocol=protocol)
        self.message_handler.configure_for_experiment(
            experiment_descriptor=experiment_descriptor, my_role=protocol.role
        )
        self.game_client.game_uuid = experiment_descriptor.game_uuid

    @override
    @logfire.instrument("Send dialogue message")
    async def send_dialogue_message(self, message: str) -> None:
        """Send the dialogue message to the other player(s)."""
        await self.message_handler.send_message(message=message)
        logger.debug("Sent dialogue message", message=message, current_role=self.protocol.role)

    @override
    async def send_game_action(self, action: KtaneGameplayInput) -> None:
        """Send a game action to the current game."""
        await self.game_client.send_action(action=action)
        logger.debug("Sent action to game", action=action, current_role=self.protocol.role)
