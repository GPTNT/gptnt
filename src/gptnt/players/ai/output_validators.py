from contextlib import suppress
from copy import deepcopy

import structlog
from json_repair import repair_json
from pydantic import ValidationError
from pydantic.type_adapter import TypeAdapter
from pydantic_ai.messages import ModelMessage, TextPart, ToolReturnPart

from gptnt.players.actions import PlayerOutputType

log = structlog.get_logger()


class InvalidOutputFormatError(ValueError):
    """Exception raised when the output format is invalid."""

    def __init__(self, *, output: str, expected_type: type) -> None:
        super().__init__("Output format is invalid")
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
    output = output.strip().replace("```json", "").replace("```", "").strip()

    with suppress(ValidationError):
        return TypeAdapter(output_type).validate_json(output)

    with suppress(ValidationError):
        log.debug("Trying with `json-repair`", output=output)
        output = repair_json(output)
        return TypeAdapter(output_type).validate_json(output)  # noqa: WPS336

    raise InvalidOutputFormatError(output=output, expected_type=output_type)


def set_output_tool_for_message(
    messages: list[ModelMessage], return_content_as_json: str
) -> list[ModelMessage]:
    """Set the output tool return for the messages.

    This copy-pastes what Pydantic AI does, but adds in the text part too.

    This is mainly needed to get the dummy model to work.
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
