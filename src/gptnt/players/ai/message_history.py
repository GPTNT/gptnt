import copy
import json
from contextlib import suppress
from dataclasses import dataclass, field

import logfire
import structlog
from pydantic_ai import (
    BaseToolCallPart,
    BinaryContent,
    ModelResponse,
    RunUsage,
    TextPart,
    ToolReturnPart,
)
from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart

from gptnt.ktane.game_settings import KtaneSettings
from gptnt.players.actions import PlayerOutputType
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

    This also works when there is a manual in the first message too, since we can just remove the
    last binary content which will be the last observation added after the manual.
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


def coerce_tool_output_into_native_output(messages: list[ModelMessage]) -> list[ModelMessage]:  # noqa: WPS231
    """Coerce tool output messages into the native output messages.

    This is needed when we are using ToolOutput but we don't want to then give them back to the
    model, so we clean up afterwards.

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

            # if it's empty, continue, otherwise we gotta keep the message
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

        # Make sure we fix any ToolOutput messages into NativeOutput messages
        new_messages = coerce_tool_output_into_native_output(new_messages)

        if self.protocol.role == "defuser":
            new_messages = self._remove_observations_from_messages(new_messages)

        # Remove any empty messages
        self.messages.append(new_messages)

    def replace_last_response_with_action(self, *, action: PlayerOutputType) -> None:
        """Replace the last response in the message history with a do-nothing action.

        This is useful when some other validator/parser goes wrong after the model has done its
        output and we need to just track that instead of performing an action, the model just did
        nothing.
        """
        if self.is_empty:
            return

        # We know that this should be a ModelResponse
        assert isinstance(self.messages[-1][-1], ModelResponse)

        # And then we replace the last part with the action
        self.messages[-1][-1].parts = [TextPart(action.text_part_dump())]

    def truncate_history_if_needed(self) -> None:
        """Truncate the message history to fit within the usage limits."""
        if self.capabilities.usage_limits.input_tokens_limit is None:
            # If there is no limit, we never truncate
            return

        if not self._should_truncate_message_history():
            return

        with logfire.span("Truncate message history"):
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

    @logfire.instrument("Remove observations from messages", extract_args=False)
    def _remove_observations_from_messages(
        self, new_messages: list[ModelMessage]
    ) -> list[ModelMessage]:
        """Remove observations from the messages (and also update the usage)."""
        updated_messages: list[ModelMessage] = []
        num_observations_removed = 0

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
            # if we have the number of tokens in the prompt, just use that.
            if self.usage.details.get("image_prompt_tokens"):
                tokens_to_remove = self.usage.details["image_prompt_tokens"]
            else:
                tokens_to_remove = num_observations_removed * self.tokens_per_image

            new_value = self.usage.input_tokens - tokens_to_remove
            if new_value < 0:
                logger.warning(
                    f"Token correction would go negative: {self.usage.input_tokens=} "
                    f"- {tokens_to_remove=} -> clamping to 0"
                )
                new_value = 0
            self.usage.input_tokens = new_value
        return updated_messages

    def _does_message_contain_manual(self, message: ModelMessage) -> bool:
        """Check if the message will have the manual in it.

        Use the player protocol and other things to figure it out. Importantly, when the message
        history is empty, we know that the first message will have the manual in it.
        """
        return self.protocol.include_manual and self.is_empty and isinstance(message, ModelRequest)

    def _should_truncate_message_history(self, *, next_message: str | None = None) -> bool:
        """Check if the context length is over the max context length."""
        if self.capabilities.usage_limits.input_tokens_limit is None:
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
            self.capabilities.usage_limits.input_tokens_limit * self.truncation_threshold
        )
