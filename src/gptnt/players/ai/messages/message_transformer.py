import copy
import json

from pydantic_ai import BaseToolCallPart, BinaryContent, ModelResponse, TextPart, ToolReturnPart
from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart


def remove_binary_content_from_model_request(
    message: ModelRequest, *, keep_last_observation: bool
) -> tuple[int, ModelRequest]:
    """Remove binary content (observations) from a model request.

    Args:
        message: The model request to clean
        keep_last_observation: If True, keeps the last BinaryContent in each part

    Returns:
        Tuple of (number of observations removed, cleaned message)
    """
    num_removed = 0
    clean_message = copy.deepcopy(message)

    for part in clean_message.parts:
        if not isinstance(part, UserPromptPart) or isinstance(part.content, str):
            continue

        content_list = list(part.content)

        num_observations = sum(1 for piece in content_list if isinstance(piece, BinaryContent))
        # For the remaining parts, remove all binary content except optionally the last one
        binary_indices = [
            idx for idx, piece in enumerate(content_list) if isinstance(piece, BinaryContent)
        ]
        # Determine which indices to keep
        keep_indices = set(binary_indices[-1:]) if keep_last_observation else set()

        # Remove any indices that are not in keep_indices
        remaining_parts = [
            piece
            for idx, piece in enumerate(content_list)
            if idx in keep_indices or not isinstance(piece, BinaryContent)
        ]
        num_removed += num_observations - len(keep_indices)
        part.content = remaining_parts
    return num_removed, clean_message


def ensure_messages_have_valid_final_response(messages: list[ModelMessage]) -> list[ModelMessage]:
    """Ensure that the message list ends with a model response that has at least one TextPart."""
    if not messages:
        return messages

    # If there is no response anywhere within the messages, we need to add one
    if not any(isinstance(message, ModelResponse) for message in messages):
        messages.append(ModelResponse([TextPart("")]))

    return messages


def coerce_tool_output_into_native_output(messages: list[ModelMessage]) -> list[ModelMessage]:  # noqa: WPS231
    """Coerce tool output messages into native output messages.

    This is needed when we are using ToolOutput but we don't want to give them back to the model,
    so we clean up afterwards.

    Importantly, because we are using tools as a medium for structured outputs, we are making
    certain assumptions. These assumptions CANNOT be made if you are using tools as tools, allowing
    models to use the tool responses. That makes everything different and WILL break things, but
    that's not a use case we are currently supporting.
    """
    fixed_messages: list[ModelMessage] = []

    for message in messages:
        if isinstance(message, ModelRequest):
            # Remove any ToolReturnPart from the message
            fixed_parts = [part for part in message.parts if not isinstance(part, ToolReturnPart)]

            # If it's empty, continue, otherwise we gotta keep the message
            if not fixed_parts:
                continue

            fixed_message = copy.deepcopy(message)
            fixed_message.parts = fixed_parts
            fixed_messages.append(fixed_message)

        if isinstance(message, ModelResponse):
            new_parts = []
            for part in message.parts:
                if isinstance(part, BaseToolCallPart):
                    fixed_func_call = {
                        "result": {
                            "kind": part.tool_name.replace("final_result_", ""),
                            "data": part.args_as_dict(),
                        }
                    }
                    new_parts.append(
                        TextPart(
                            content=json.dumps(fixed_func_call),
                            provider_details=part.provider_details,
                        )
                    )
                else:
                    new_parts.append(part)

            fixed_message = copy.deepcopy(message)
            fixed_message.parts = new_parts
            fixed_messages.append(fixed_message)

    return fixed_messages
