from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass
from typing import Union, override

import logfire
import structlog
from pydantic_ai import BinaryContent
from pydantic_ai.messages import ModelMessage

from gptnt.ktane.manual import MANUAL_NUM_PAGES, KtaneManualPaths
from gptnt.players.actions import DoNothingAction, SendMessageAction
from gptnt.players.ai.ai_player import AIPlayer

log = structlog.get_logger()

type ExpertOutputT = Union[SendMessageAction, DoNothingAction]  # noqa: UP007
"""Possible structured output types for the Expert.

Note: Needs to be Union until PEP-747 lands.
https://ai.pydantic.dev/results/#structured-result-validation
"""


def load_manual_as_prompt(*, num_pages: int = MANUAL_NUM_PAGES) -> Iterator[str | BinaryContent]:
    """Load the content for the manual."""
    log.debug(f"Loading {num_pages} pages of the manual")
    manual_paths = KtaneManualPaths()

    for page_num in range(1, num_pages + 1):
        # Load the text for the page first
        yield manual_paths.load_text(page_num)

        # Load the image for the page afterwards
        image = manual_paths.load_image(page_num, kind="512")
        yield BinaryContent(image, media_type="image/png")


@dataclass(kw_only=True)
class ExpertPlayer(AIPlayer[None, ExpertOutputT]):
    """Class for all Expert players."""

    @override
    @logfire.instrument("Build agent input")
    async def build_agent_input(self) -> str | list[str | BinaryContent]:
        """Build the input for the expert.

        For the first message, we also load the manual within the prompt too.
        """
        # If there is a history, we just pull the unread messages
        if self._message_history:
            return await self.pull_unread_messages_from_dialogue_space()

        # If we have no messages, we need to load the manual as the prompt
        # This is a bit of a hack, but we need to load the manual as the prompt
        # since the AI model doesn't support loading the manual as a prompt
        messages = [
            *list(load_manual_as_prompt()),
            await self.pull_unread_messages_from_dialogue_space(),
        ]
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

    @override
    def add_new_messages_to_history(self, messages: list[ModelMessage]) -> None:
        """Add new messages to the message history."""
        self._message_history.extend(messages)
