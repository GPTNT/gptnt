from contextlib import suppress
from typing import Any

import structlog
from json_repair import repair_json
from pydantic import TypeAdapter, ValidationError
from pydantic_core import from_json

log = structlog.get_logger()


class InvalidOutputFormatError(ValueError):
    """Exception raised when the output format is invalid."""

    def __init__(self, *, output: str, expected_type: type) -> None:
        message = f"Output format is invalid. Output does not parse to expected type {expected_type!r}, got output: {output!r}"
        super().__init__(message)
        self.output = output
        self.expected_type = expected_type


def _extract_from_nested_output_dict(output: dict[str, Any] | Any) -> dict[str, Any]:
    """Extract the actual output from nested dict.

    This is because the default output schema from pydantic-ai wraps the output in a nested dict.
    """
    if (
        isinstance(output, dict)  # noqa: WPS222
        and "result" in output
        and isinstance(output["result"], dict)
        and "data" in output["result"]
        and isinstance(output["result"]["data"], dict)
    ):
        return output["result"]["data"]
    return output


def structure_string_output[OutputT](
    *, output: str | OutputT, output_type: type[OutputT]
) -> OutputT:
    """Structure the output from the agent.

    This will be used to structure the output from the agent.
    """
    if not isinstance(output, str):
        return output
    output = output.strip().replace("```json", "").replace("```", "").strip()

    clean_output = repair_json(output)

    try:
        output_as_json = from_json(clean_output)
    except ValueError as err:
        raise InvalidOutputFormatError(output=output, expected_type=output_type) from err

    output_as_json = _extract_from_nested_output_dict(output_as_json)
    with suppress(ValidationError):
        return TypeAdapter(output_type).validate_python(output_as_json)

    raise InvalidOutputFormatError(output=output, expected_type=output_type)
