from contextlib import suppress
from copy import deepcopy
from typing import NamedTuple, Self

import structlog
from pydantic import ValidationError
from pydantic.type_adapter import TypeAdapter
from pydantic_ai.messages import ModelMessage, TextPart, ToolReturnPart
from pydantic_ai.usage import Usage

from gptnt.players.actions import DoNothingAction, PlayerOutputType

log = structlog.get_logger()


class InvalidOutputFormatError(Exception):
    """Exception raised when the output format is invalid."""

    def __init__(self, message: str, output: str, expected_type: type) -> None:
        super().__init__(message)
        self.output = output
        self.expected_type = expected_type


def structure_string_output(
    *, output: str | PlayerOutputType, output_type: type[PlayerOutputType]
) -> PlayerOutputType:
    """Structure the output from the agent.

    This will be used to structure the output from the agent.
    """
    if not isinstance(output, str):
        return output
    output = output.strip().replace("```json", "").replace("```", "")

    with suppress(ValidationError):
        return TypeAdapter(output_type).validate_json(output)

    with suppress(ValidationError):
        log.warning('Trying with the `"}` on the end', output=output)
        return TypeAdapter(output_type).validate_json(output + '"}')  # noqa: WPS336

    raise InvalidOutputFormatError(
        "Output format is invalid.", output=output, expected_type=output_type
    )


def set_output_tool_for_message(
    messages: list[ModelMessage], return_content_as_json: str
) -> list[ModelMessage]:
    """Set the output tool return for the messages.

    This copy-pastes what Pydantic AI does, but adds in the text part too.
    """
    messages = deepcopy(messages)
    last_message = messages[-1]
    for part in last_message.parts:
        if isinstance(part, ToolReturnPart):
            part.content = return_content_as_json
            return messages
        if isinstance(part, TextPart):
            part.content = return_content_as_json
            return messages

    raise LookupError("Could not find the last message to set the output to")


class AgentOutput(NamedTuple):
    """Model output for the AI player."""

    output: PlayerOutputType
    usage: Usage
    messages: list[ModelMessage]

    @classmethod
    def do_nothing(cls) -> Self:
        """Return an empty agent output."""
        return cls(output=DoNothingAction(), usage=Usage(), messages=[])

    @classmethod
    def with_message_cleanup(
        cls, *, output: PlayerOutputType, usage: Usage, new_messages: list[ModelMessage]
    ) -> Self:
        """Return an agent output from the agent return."""
        return cls(
            output=output,
            usage=usage,
            # TODO: This is where the dummy model is flagging the failure the failure so this
            #       needs fixing.
            messages=set_output_tool_for_message(
                messages=new_messages, return_content_as_json=output.model_dump_json()
            ),
        )
