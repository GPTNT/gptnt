import copy
import json

from pydantic_ai import BaseToolCallPart, ModelResponse, TextPart, ToolReturnPart
from pydantic_ai.messages import ModelMessage, ModelRequest


def _coerce_request(message: ModelRequest) -> ModelRequest | None:
    kept_parts = [part for part in message.parts if not isinstance(part, ToolReturnPart)]
    if len(kept_parts) == len(message.parts):
        return message
    if not kept_parts:
        return None
    coerced = copy.deepcopy(message)
    coerced.parts = kept_parts
    return coerced


def _coerce_response(message: ModelResponse) -> ModelResponse:
    if not any(isinstance(part, BaseToolCallPart) for part in message.parts):
        return message

    new_parts = [
        TextPart(
            content=json.dumps(
                {
                    "result": {
                        "kind": part.tool_name.replace("final_result_", ""),
                        "data": part.args_as_dict(),
                    }
                }
            ),
            provider_details=part.provider_details,
        )
        if isinstance(part, BaseToolCallPart)
        else part
        for part in message.parts
    ]
    coerced = copy.deepcopy(message)
    coerced.parts = new_parts
    return coerced


def coerce_tool_output_into_native_output(messages: list[ModelMessage]) -> list[ModelMessage]:
    """Coerce tool output messages into native output messages.

    This is needed when we are using ToolOutput but we don't want to give them back to the model,
    so we clean up afterwards.

    Importantly, because Pydantic AI uses tools as a medium for structured outputs, it makes
    certain assumptions. These assumptions CANNOT be made if you are using tools as tools, allowing
    models to use the tool responses. That makes everything different and WILL break things, but
    that's not a use case we are currently supporting.
    """
    coerced: list[ModelMessage] = []
    for message in messages:
        if isinstance(message, ModelRequest):
            request = _coerce_request(message)
            if request is not None:
                coerced.append(request)
        else:
            coerced.append(_coerce_response(message))
    return coerced
