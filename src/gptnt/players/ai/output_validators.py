from contextlib import suppress

import structlog
from json_repair import repair_json
from pydantic import ValidationError
from pydantic.type_adapter import TypeAdapter

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
