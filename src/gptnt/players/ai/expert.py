from collections.abc import Awaitable, Callable
from typing import Union, override

import structlog

from gptnt.players.actions import DoNothingAction, SendMessageAction
from gptnt.players.ai.ai_player import AIPlayer

log = structlog.get_logger()

type ExpertResultT = Union[SendMessageAction, DoNothingAction]  # noqa: UP007
"""Possible structured output types for the Expert.

Note: Needs to be Union until PEP-747 lands.
https://ai.pydantic.dev/results/#structured-result-validation
"""


class ExpertPlayer(AIPlayer[None, ExpertResultT]):
    """Class for all Expert players."""

    role = "expert"

    @override
    async def build_agent_input(self) -> str:
        """Build the input for the expert."""
        messages = await self.pull_unread_messages_from_dialogue_space()
        return messages

    @override
    def agent_result_type_to_function(
        self, result_type: type[ExpertResultT]
    ) -> Callable[[ExpertResultT], Awaitable[None]]:
        """Map the result type from the AI model to a method within the function.

        This will allow us to dynamically convert the result from the AI model to a function that
        can be called to carry the logic forwards.
        """
        switcher: dict[type[ExpertResultT], Callable[..., Awaitable[None]]] = {
            SendMessageAction: self.send_message_to_dialogue_space,
            DoNothingAction: self.do_nothing_action,
        }
        return switcher[result_type]

    @override
    def build_deps_for_request(self) -> None:
        """Return None since this class doesn't use tools or have deps."""
        return  # noqa: WPS324
