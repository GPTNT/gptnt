import copy
from contextlib import suppress
from dataclasses import dataclass, field

import logfire
import pydantic_core
import structlog
from pydantic_ai import BinaryContent, RunUsage
from pydantic_ai.messages import (
    BaseToolCallPart,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from gptnt.ktane.game_settings import KtaneSettings
from gptnt.players.ai.tokens import count_tokens_from_text, estimate_tokens_for_image_per_model
from gptnt.players.specification import PlayerCapabilities, PlayerProtocol

logger = structlog.get_logger()

type AgentMessageInput = str | list[str | BinaryContent]


def remove_observations_without_removing_manual(part: UserPromptPart) -> UserPromptPart:
    """Remove observations from the first message without removing the manual.

    When this is the case, the role is the defuser and this will be the first message of the game.
    As a result, there will be no text input (we hope unless someone is running that experiment) so
    we will just remove the very last binary content from the all the binary contents in the
    message.
    """
    if isinstance(part.content, str):
        return part

    content = list(part.content)
    content.reverse()
    with suppress(ValueError, StopIteration):
        last_observation_index = content.index(
            next(piece for piece in content if isinstance(piece, BinaryContent))
        )
        _ = content.pop(last_observation_index)
    content.reverse()
    return UserPromptPart(content=content)


def remove_all_binary_content_from_user_prompt(part: UserPromptPart) -> tuple[int, UserPromptPart]:
    """Remove all binary content from the user prompt part."""
    if isinstance(part.content, str):
        return 0, part

    new_content = [piece for piece in part.content if not isinstance(piece, BinaryContent)]
    num_removed = len(part.content) - len(new_content)
    part.content = new_content
    return num_removed, part


def remove_binary_content_from_model_request(
    message: ModelRequest, *, message_contains_manual: bool
) -> tuple[int, ModelRequest]:
    """Remove all binary content from the model request.

    If the message contains the manual, then we will not remove the manual but we will (try) to
    remove any observations that might be in there.
    """
    num_removed = 0

    # copy the message but dont copy the parts since we're going to modify them
    clean_message = copy.deepcopy(message)
    clean_message.parts = []

    for part in message.parts:
        cleaned_part = part
        if isinstance(part, UserPromptPart):
            if message_contains_manual:
                cleaned_part = remove_observations_without_removing_manual(part)
                num_removed += 1
            else:
                removed, cleaned_part = remove_all_binary_content_from_user_prompt(part)
                num_removed += removed

        clean_message.parts.append(cleaned_part)
    return num_removed, clean_message


def remove_thoughts_from_tool_call(tool_call_part: ToolCallPart) -> ToolCallPart:
    """Remove thoughts from the tool call part."""
    try:
        tool_args = tool_call_part.args_as_dict()
    except (AssertionError, ValueError):
        logger.warning("tool args were not a valid json dict", args=tool_call_part.args)
        return tool_call_part

    tool_call_part.args = tool_args
    if "thoughts" in tool_call_part.args:
        tool_call_part.args["thoughts"] = None
    return tool_call_part


TOOL_RETURN_TO_IGNORE = frozenset(("Final result processed.",))


def remove_thought_from_tool_return(tool_return_part: ToolReturnPart) -> ToolReturnPart:
    """Remove thoughts from the tool return part."""
    try:
        structured_output = pydantic_core.from_json(tool_return_part.content)
    except ValueError:
        # Often, its one of these values that we don't care about so we can skip the log
        if tool_return_part.content not in TOOL_RETURN_TO_IGNORE:
            logger.warning(
                "tool return part was not a valid json dict", args=tool_return_part.content
            )
        return tool_return_part

    # Remove the thoughts from the content
    if "thoughts" in structured_output:
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
        # If we are using structured outputs, this is then blank so we can just skip the log
        if text_part.content:
            logger.warning("text part was not a valid json dict", args=text_part.content)
        return text_part

    if "thoughts" in structured_output:
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


def remove_any_empty_messages(messages: list[ModelMessage]) -> list[ModelMessage]:  # noqa: WPS231
    """Remove any empty messages from the list."""
    cleaned_messages: list[ModelMessage] = []
    for message in messages:
        valid_parts = []
        for part in message.parts:
            if isinstance(part, BaseToolCallPart):
                if part.args:
                    valid_parts.append(part)
            elif part.content:
                valid_parts.append(part)

        if valid_parts:
            message.parts = valid_parts
            cleaned_messages.append(message)
    return cleaned_messages


@dataclass(kw_only=True)
class MessageHistory:
    """Hold and manage the message history for the AI player.

    This handles all the logic for building and modifying the history.
    """

    capabilities: PlayerCapabilities
    protocol: PlayerProtocol

    messages: list[list[ModelMessage]] = field(default_factory=list)
    """Message history of the player."""

    usage: RunUsage = field(default_factory=RunUsage)
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
            model=self.capabilities.player_name,
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

    def update(self, *, new_messages: list[ModelMessage], usage: RunUsage) -> None:
        """Update the message history given the player spec.

        This will modify the message history in place. The default behaviour is to do nothing, and
        only modify it by removing things.
        """
        # Update usage BEFORE modifying the messages
        self.usage = usage

        if self.protocol.role == "defuser":
            new_messages = self._remove_observations_from_messages(new_messages)

        if not self.protocol.allow_outputs_in_history:
            new_messages = [message for message in new_messages if not is_model_output(message)]

        if not self.protocol.allow_thoughts_in_history:
            new_messages = [
                remove_thoughts_from_model_message(message) for message in new_messages
            ]

        # Remove any empty messages
        new_messages = remove_any_empty_messages(new_messages)
        self.messages.append(new_messages)

    @logfire.instrument("Truncate message history")
    def truncate_history_if_needed(self) -> None:
        """Truncate the message history to fit within the usage limits."""
        if self.capabilities.usage_limits.request_tokens_limit is None:
            # If there is no limit, we never truncate
            return

        while self._should_truncate_message_history():
            history = self.messages
            # Remove messages but not the manual
            if self.protocol.include_manual and self.num_times_truncated == 0:
                # For the first one, reset the content within the message with the manual
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

    @logfire.instrument("Remove observations from messages")
    def _remove_observations_from_messages(
        self, new_messages: list[ModelMessage]
    ) -> list[ModelMessage]:
        """Remove observations from the messages (and also update the usage)."""
        updated_messages: list[ModelMessage] = []
        num_observations_removed = 0

        # TODO: This needs fixing to work for solo player to distinguish the manual from
        #       observations
        for message in new_messages:
            if isinstance(message, ModelRequest):
                contains_manual = self._does_message_contain_manual(message)
                num_removed, clean_message = remove_binary_content_from_model_request(
                    message, message_contains_manual=contains_manual
                )
                num_observations_removed += num_removed
                updated_messages.append(clean_message)
            else:
                updated_messages.append(message)

        # Update the usage to reflect the number of observation tokens removed
        if num_observations_removed > 0 and self.usage.input_tokens > 0:
            # TODO: Needs fixing because somehow it's resulting in negative tokens
            self.usage.input_tokens -= num_observations_removed * self.tokens_per_image
        return updated_messages

    def _does_message_contain_manual(self, message: ModelMessage) -> bool:
        """Check if the message will have the manual in it.

        Use the player protocol and other things to figure it out. Importantly, when the message
        history is empty, we know that the first message will have the manual in it.
        """
        return (
            self.protocol.include_manual
            and self.protocol.role == "defuser"
            and self.is_empty
            and isinstance(message, ModelRequest)
        )

    def _should_truncate_message_history(self, *, next_message: str | None = None) -> bool:
        """Check if the context length is over the max context length."""
        if self.capabilities.usage_limits.request_tokens_limit is None:
            # If there is no limit, we never truncate
            return False

        model_input = self.usage.input_tokens or 0
        # Add in any extra tokens for the maximum number of images we would need
        model_input += self.tokens_per_image * self.capabilities.max_observation_window_length
        # Also add in the tokens for the next message if we have one
        if next_message:
            model_input += count_tokens_from_text(next_message)

        # Check if we are over the context length
        return model_input > (
            self.capabilities.usage_limits.request_tokens_limit * self.truncation_threshold
        )
