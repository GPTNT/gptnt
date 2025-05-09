from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Union, override

import logfire
import structlog
from pydantic import TypeAdapter, ValidationError
from pydantic_ai import BinaryContent

from gptnt.players.actions import DoNothingAction, SendMessageAction
from gptnt.players.ai.ai_player import AIPlayer
from gptnt.players.ai.prompts import load_manual_as_prompt

log = structlog.get_logger()

type ExpertOutputT = Union[SendMessageAction, DoNothingAction]  # noqa: UP007
"""Possible structured output types for the Expert.

Note: Needs to be Union until PEP-747 lands.
https://ai.pydantic.dev/results/#structured-result-validation
"""


@dataclass(kw_only=True)
class ExpertPlayer(AIPlayer[None, ExpertOutputT]):
    """Class for all Expert players."""

    @override
    def coerce_model_string_outputs(self, output: str) -> ExpertOutputT:
        output = output.strip().replace("```json", "").replace("```", "")
        try:
            return TypeAdapter(ExpertOutputT).validate_json(output)
        except ValidationError:
            log.warning('Trying with the `"}` on the end', output=output)
            return TypeAdapter(ExpertOutputT).validate_json(output + '"}')  # noqa: WPS336

    @override
    @logfire.instrument("Build agent input")
    async def build_agent_input(self) -> str | list[str | BinaryContent]:
        """Build the input for the expert.

        For the first message, we also load the manual within the prompt too.
        """
        new_messages = await self.pull_unread_messages_from_dialogue_space()

        # If there is a history, we just pull the unread messages
        if self.player_usage.message_history:
            return new_messages

        # If we have no messages, we need to load the manual as the prompt
        # This is a bit of a hack, but we need to load the manual as the prompt
        # since the AI model doesn't support loading the manual as a prompt
        messages = [*load_manual_as_prompt(), new_messages]
        return messages

    @override
    def agent_output_type_to_function(
        self, output_type: type[ExpertOutputT]
    ) -> Callable[[ExpertOutputT], Awaitable[None]]:
        switcher: dict[type[ExpertOutputT], Callable[..., Awaitable[None]]] = {
            SendMessageAction: self.send_message_to_dialogue_space,
            DoNothingAction: self.do_nothing_action,
        }
        return switcher[output_type]

    @override
    def build_deps_for_request(self) -> None:
        """Return None since this class doesn't use tools or have deps."""
        return  # noqa: WPS324
