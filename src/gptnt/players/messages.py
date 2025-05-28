from dataclasses import dataclass, field

import pydantic_core
import structlog
from pydantic_ai import BinaryContent
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.usage import Usage

from gptnt.ktane.game_settings import KtaneSettings
from gptnt.ktane.manual import MANUAL_PAGE_IDENTIFIER_STRING
from gptnt.players.spec import PlayerMetadata, PlayerSpec
from gptnt.players.tokens import count_tokens_from_text, estimate_tokens_for_image_per_model

logger = structlog.get_logger()

type AgentMessageInput = str | list[str | BinaryContent]


def remove_binary_content_from_user_message(message: ModelMessage) -> tuple[int, ModelMessage]:
    """Remove binary content from the message."""
    num_removed = 0
    if isinstance(message, ModelRequest):
        for part in message.parts:
            # Check if its a thing we need to remove binary content from
            if isinstance(part, UserPromptPart) and isinstance(part.content, list):
                new_part_content = [
                    piece for piece in part.content if not isinstance(piece, BinaryContent)
                ]
                num_removed = len(part.content) - len(new_part_content)
                part.content = new_part_content
    return num_removed, message


def remove_thoughts_from_tool_call(tool_call_part: ToolCallPart) -> ToolCallPart:
    """Remove thoughts from the tool call part."""
    try:
        tool_args = tool_call_part.args_as_dict()
    except (AssertionError, ValueError):
        logger.warning("tool args were not a valid json dict", args=tool_call_part.args)
    else:
        tool_call_part.args = tool_args
        tool_call_part.args["thoughts"] = None
    return tool_call_part


def remove_thought_from_tool_return(tool_return_part: ToolReturnPart) -> ToolReturnPart:
    """Remove thoughts from the tool return part."""
    try:
        structured_output = pydantic_core.from_json(tool_return_part.content)
    except ValueError:
        logger.warning("tool return part was not a valid json dict", args=tool_return_part.content)
        return tool_return_part

    # Remove the thoughts from the content
    structured_output["thoughts"] = None
    tool_return_part.content = pydantic_core.to_json(structured_output).decode()

    return tool_return_part


def remove_thoughts_from_text(text_part: TextPart) -> TextPart:
    """Remove thoughts from the text part.

    This happens when the model just doesn't support structured outputs.
    """
    try:
        structured_output = pydantic_core.from_json(text_part.content)
    except ValueError:
        logger.warning("text part was not a valid json dict", args=text_part.content)
        return text_part

    structured_output["thoughts"] = None
    text_part.content = pydantic_core.to_json(structured_output).decode()

    return text_part


def remove_thoughts_from_model_message(message: ModelMessage) -> ModelMessage:
    """Remove thoughts from the message."""
    new_parts = []
    for part in message.parts:
        if isinstance(part, ToolCallPart):
            new_parts.append(remove_thoughts_from_tool_call(part))
        elif isinstance(part, ToolReturnPart):
            new_parts.append(remove_thought_from_tool_return(part))
        elif isinstance(part, TextPart):
            new_parts.append(remove_thoughts_from_text(part))
    return message


def is_model_output(message: ModelMessage) -> bool:
    """Check if the message is a model output."""
    # if its an explicit response, then its the output
    if isinstance(message, ModelResponse):
        return True

    # Handle the case where requests are the processed tool calls
    return any(isinstance(part, ToolReturnPart) for part in message.parts)


def does_message_contain_manual(message: ModelRequest) -> bool:  # noqa: WPS231
    """Check if the message is the manual.

    It's a bit of a hack, but I can't think of a better way to do this right now.
    """
    for part in message.parts:
        if isinstance(part, UserPromptPart) and isinstance(part.content, list):
            for content in part.content:
                if isinstance(content, str) and MANUAL_PAGE_IDENTIFIER_STRING in content:
                    return True
    return False


@dataclass(kw_only=True)
class MessageHistory:
    """Hold and manage the message history for the AI player.

    This handles all the logic for building and modifying the history.
    """

    metadata: PlayerMetadata
    spec: PlayerSpec

    messages: list[list[ModelMessage]] = field(default_factory=list)
    """Message history of the player."""

    usage: Usage = field(default_factory=Usage)
    """Usage statistics for the last request."""

    num_times_truncated: int = 0
    """Number of times the message history has been truncated."""

    truncation_threshold: float = 0.9
    """Threshold for truncation of the message history."""

    @property
    def tokens_per_image(self) -> int:
        """Estimate the number of tokens per image for the current model."""
        ktane_settings = KtaneSettings()
        return estimate_tokens_for_image_per_model(
            model=self.metadata.player_name,
            width=ktane_settings.game_width,
            height=ktane_settings.game_height,
        )

    @property
    def is_empty(self) -> bool:
        """Check if the message history is empty."""
        return len(self.messages) == 0

    def __bool__(self) -> bool:
        """Check if the player has any messages."""
        return bool(self.messages)

    def __len__(self) -> int:
        """Get the number of messages in the history."""
        return len(self.messages)

    def to_history(self) -> list[ModelMessage]:
        """Get the message history."""
        return [message for messages in self.messages for message in messages]

    def update(self, *, new_messages: list[ModelMessage], usage: Usage) -> None:
        """Update the message history given the player spec.

        This will modify the message history in place. The default behaviour is to do nothing, and
        only modify it by removing things.
        """
        # update usage BEFORE modifying the messages
        self.usage = usage

        if self.spec.role == "defuser":
            new_messages = self._remove_observations_from_messages(new_messages)

        if not self.spec.allow_outputs_in_history:
            new_messages = [message for message in new_messages if not is_model_output(message)]

        if not self.spec.allow_thoughts_in_history:
            new_messages = [
                remove_thoughts_from_model_message(message) for message in new_messages
            ]
        self.messages.append(new_messages)

    def truncate_history_if_needed(self) -> None:
        """Truncate the message history to fit within the usage limits."""
        if self.metadata.usage_limits.request_tokens_limit is None:
            # If there is no limit, we never truncate
            return

        while self._should_truncate_message_history():
            history = self.messages
            # Remove messages but not the manual
            if self.spec.include_manual and self.num_times_truncated == 0:
                # for the first one, reset the content within the message with the manual
                assert isinstance(history[0][0], ModelRequest)
                assert isinstance(history[0][0].parts[0], UserPromptPart)
                manual_prompt = history[0][0].parts[0]
                assert isinstance(manual_prompt.content, list)
                _ = manual_prompt.content.pop(-1)
            else:
                # Note: Raises IndexError if list is empty or index is out of range.
                _ = history.pop(1)

            self.num_times_truncated += 1
            self.messages = history

    def _remove_observations_from_messages(
        self, new_messages: list[ModelMessage]
    ) -> list[ModelMessage]:
        """Remove observations from the messages (and also update the usage)."""
        updated_messages: list[ModelMessage] = []
        num_observations_removed = 0

        for message in new_messages:
            if isinstance(message, ModelRequest) and not does_message_contain_manual(message):
                num_removed, clean_message = remove_binary_content_from_user_message(message)
                num_observations_removed += num_removed
                updated_messages.append(clean_message)
            else:
                updated_messages.append(message)

        # Update the usage to reflect the number of observation tokens removed
        if num_observations_removed > 0 and self.usage.request_tokens is not None:
            self.usage.request_tokens -= num_observations_removed * self.tokens_per_image
        return updated_messages

    def _should_truncate_message_history(self, *, next_message: str | None = None) -> bool:
        """Check if the context length is over the max context length."""
        if self.metadata.usage_limits.request_tokens_limit is None:
            # If there is no limit, we never truncate
            return False

        model_input = self.usage.request_tokens or 0
        # Add in any extra tokens for the maximum number of images we would need
        model_input += self.tokens_per_image * self.metadata.max_observation_window_length
        # Also add in the tokens for the next message if we have one
        if next_message:
            model_input += count_tokens_from_text(next_message)

        # Check if we are over the context length
        return model_input > (
            self.metadata.usage_limits.request_tokens_limit * self.truncation_threshold
        )
