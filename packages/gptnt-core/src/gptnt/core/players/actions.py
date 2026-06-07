import json
from typing import Generic, Literal

from pydantic import BaseModel, ConfigDict

from gptnt.core.ktane.actions import GameActionType, KtaneBaseAction
from gptnt.core.players.locations import InteractableLocation, LocationDataT_co

NO_NEW_MESSAGES_SENTINEL = "<no_new_messages>"
"""Sentinel for no new messages."""


class ModelOutputDumpsMixin(BaseModel):
    """Mixin for dumping actions to conform to the JSONSchema from NativeOutput."""

    def text_part_dump(self) -> str:
        """Dump the model output as a string."""
        return json.dumps(
            {
                "result": {
                    "kind": self.model_config.get("title", self.__class__.__name__),
                    "data": self.model_dump(
                        mode="json", exclude_defaults=True, exclude_unset=True
                    ),
                }
            }
        )


class DoNothingAction(ModelOutputDumpsMixin):
    """Create a 'do nothing' action."""

    model_config = ConfigDict(title="do_nothing")


class SendMessageAction(ModelOutputDumpsMixin):
    """Create a 'send message' action."""

    model_config = ConfigDict(title="send_message")

    message: str


class InteractGameAction(
    KtaneBaseAction[GameActionType, LocationDataT_co],
    ModelOutputDumpsMixin,
    Generic[LocationDataT_co],  # noqa: UP046
):
    """Interaction action for the player to take in the game."""

    model_config = ConfigDict(title="interact_game")


class MagicGameAction(
    KtaneBaseAction[Literal["magic"], InteractableLocation], ModelOutputDumpsMixin
):
    """Magic action for the player to take in the game."""

    model_config = ConfigDict(title="perform_magic")


class LotteryGameAction(
    KtaneBaseAction[Literal["lottery"], InteractableLocation], ModelOutputDumpsMixin
):
    """Lottery action for the player to take in the game."""

    model_config = ConfigDict(title="perform_lottery")


type GameInteractionActionType = (
    MagicGameAction | LotteryGameAction | InteractGameAction[InteractableLocation]
)
"""Action types representing only game interaction actions."""


type PlayerOutputType = (
    DoNothingAction
    | SendMessageAction
    | InteractGameAction[InteractableLocation]
    | MagicGameAction
    | LotteryGameAction
)
"""Any possible output from a player."""
