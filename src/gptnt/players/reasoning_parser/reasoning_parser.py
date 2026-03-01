from contextlib import suppress
from dataclasses import dataclass
from typing import Any, override

import structlog
from json_repair import repair_json
from pydantic import TypeAdapter, ValidationError
from pydantic_ai import AgentRunResult
from pydantic_core import from_json

from gptnt.players.actions import AgentCallResult
from gptnt.players.exceptions import AIResponseErrorType, InvalidOutputFormatError

logger = structlog.get_logger()


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
        raise InvalidOutputFormatError(
            output=output,
            expected_type=output_type,
            response_error=[AIResponseErrorType.action_parsing_failed],
        ) from err

    output_as_json = _extract_from_nested_output_dict(output_as_json)
    with suppress(ValidationError):
        return TypeAdapter(output_type).validate_python(output_as_json)

    raise InvalidOutputFormatError(
        output=output,
        expected_type=output_type,
        response_error=[AIResponseErrorType.action_parsing_failed],
    )


@dataclass(kw_only=True)
class ReasoningParser[ModelOutputT, ParserOutputT]:
    """Base class for parsing reasoning/thinking from AI outputs.

    If you want to skip the structuring, you can set output_type to None.
    """

    def __call__(
        self, output: AgentRunResult[ModelOutputT], *, output_type: type[ParserOutputT] | None
    ) -> AgentCallResult[ParserOutputT]:
        """Parse the reasoning from the agent output."""
        raise NotImplementedError


class NoOpReasoningParser[OutputT](ReasoningParser[OutputT, OutputT]):
    """A no-op reasoning parser that returns the model output as-is."""

    @override
    def __call__(
        self, output: AgentRunResult[OutputT], *, output_type: type[OutputT] | None = None
    ) -> AgentCallResult[OutputT]:
        """Return the model output as-is."""
        if output_type is not None:
            logger.warning("output_type is provided but will be ignored in NoOpReasoningParser")

        return AgentCallResult(
            output=output.output,
            thoughts=output.response.thinking,
            usage=output.usage(),
            new_messages=output.new_messages(),
            ai_response_error=[],
            raw_output=output.response.text,
        )
