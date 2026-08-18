from dataclasses import dataclass
from typing import Any, override

import structlog
from pydantic_ai import AgentRunResult, ThinkingPart

from gptnt.players.reasoning_parser.reasoning_parser import (
    ReasoningParser,
    strip_action_envelope,
    strip_box_envelope,
    structure_string_output,
)
from gptnt.players.result import AgentCallResult

logger = structlog.get_logger()


def extract_thoughts_from_model_response(run_result: AgentRunResult[Any]) -> str | None:
    """Extract thoughts from the run result, if present.

    We only extract the thinking from the final ModelResponse's ThinkingParts. This is because we
    get the model response from PydanticAI's AgentRunResult, which does it for us.
    """
    if not run_result.new_messages():
        return None

    response = run_result.response
    thinking_parts = [
        part for part in response.parts if isinstance(part, ThinkingPart) and part.has_content()
    ]
    if not thinking_parts:
        return None

    return "\n".join(part.content for part in thinking_parts)


@dataclass(kw_only=True)
class InnerMonologueReasoningParser[OutputT](ReasoningParser[OutputT, OutputT]):
    """Parse reasoning returned separately from normal output as `ThinkingPart` objects."""

    @override
    def __call__(
        self, output: AgentRunResult[OutputT], *, output_type: type[OutputT] | None
    ) -> AgentCallResult[OutputT]:
        thoughts = extract_thoughts_from_model_response(output)
        raw_output = None
        if isinstance(output.output, str):
            cleaned_output = strip_action_envelope(strip_box_envelope(output.output))
            if cleaned_output != output.output:
                raw_output = output.output
                output.output = cleaned_output
            if output_type is not None:
                output.output = structure_string_output(
                    output=output.output, output_type=output_type
                )

        # TODO: I don't think that it's possible for this to ever be a string unless the OutputT is
        #       a string, so it'll error if it ever returns something that doesnt parse into one of
        #       the structured output types.

        return AgentCallResult(
            output=output.output,
            thoughts=thoughts,
            usage=output.usage,
            new_messages=output.new_messages(),
            ai_response_error=[],
            raw_output=raw_output,
        )
