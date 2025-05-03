from contextlib import suppress

from pydantic import BaseModel, Field
from pydantic_ai import BinaryContent
from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart
from pydantic_ai.usage import Usage

from gptnt.players.ai.tokens import count_tokens_from_text
from gptnt.players.structures import PlayerRole


def remove_binary_content_from_user_message(message: ModelMessage) -> ModelMessage:
    """Remove binary content from the message."""
    if isinstance(message, ModelRequest):
        for part in message.parts:
            # Check if its a thing we need to remove binary content from
            if isinstance(part, UserPromptPart) and isinstance(part.content, list):
                part.content = [
                    piece for piece in part.content if not isinstance(piece, BinaryContent)
                ]
    return message


class PlayerUsage(BaseModel):
    """Track requests/responses and messages from the agent."""

    role: PlayerRole | None
    """Role of the player."""

    message_history: list[list[ModelMessage]] = Field(default_factory=list)
    """Message history of the player."""

    num_requests: int = 0
    """Number of requests made to the LLM API."""

    num_images_per_message: int = 0
    """Number of images per message."""

    tokens_per_image: int = 0
    """Number of tokens per image for the current model."""

    num_times_truncated: int = 0
    truncation_threshold: float = 0.9

    request_tokens: list[int] = Field(default_factory=list)
    response_tokens: list[int] = Field(default_factory=list)

    def __bool__(self) -> bool:
        """Check if the player has any messages."""
        return bool(self.message_history)

    def __len__(self) -> int:
        """Get the number of messages in the history."""
        return len(self.message_history)

    @property
    def context_length(self) -> int:
        """Get the context length so far."""
        # remove the image tokens from each request
        request_tokens_without_images = [
            request - (self.num_images_per_message * self.tokens_per_image)
            for request in self.request_tokens
        ]

        # if the role if an expert, we do not remove the first one
        with suppress(IndexError):
            if self.role == "expert":
                request_tokens_without_images[0] = self.request_tokens[0]

        return sum(request_tokens_without_images) + sum(self.response_tokens)

    def estimate_tokens_for_next_message(self, message: str) -> int:
        """Estimate the number of tokens for the next message.

        Basically, how many tokens we are going to be requesting.
        """
        return (
            count_tokens_from_text(message) + self.tokens_per_image * self.num_images_per_message
        )

    def should_truncate_message_history(
        self, *, model_context_length: int, next_message: str | None = None
    ) -> bool:
        """Check if the context length is over the max context length."""
        model_input = self.context_length
        # Add in any extra tokens for the input images
        model_input += self.num_images_per_message * self.tokens_per_image
        # Also add in the tokens for the next message if we have one
        if next_message:
            model_input += self.estimate_tokens_for_next_message(next_message)

        # Check if we are over the context length
        return model_input > (model_context_length * self.truncation_threshold)

    def update(self, *, new_messages: list[ModelMessage], usage: Usage) -> None:
        """Add values from the output."""
        self.num_requests += 1

        if self.role == "defuser":
            new_messages = [
                remove_binary_content_from_user_message(message)
                if isinstance(message, ModelRequest)
                else message
                for message in new_messages
            ]
        self.message_history.append(new_messages)

        if usage.request_tokens is not None:
            self.request_tokens.append(usage.request_tokens - sum(self.request_tokens))
        if usage.response_tokens is not None:
            self.response_tokens.append(usage.response_tokens - sum(self.response_tokens))

    def to_history(self) -> list[ModelMessage]:
        """Get the message history."""
        return [message for messages in self.message_history for message in messages]

    def truncate_history(self) -> None:
        """Truncate the message history from the front."""
        history = self.message_history
        if self.role == "expert" and self.num_times_truncated == 0:
            # for the first one, reset the content within the message with the manual
            assert isinstance(history[0][0], ModelRequest)
            assert isinstance(history[0][0].parts[0], UserPromptPart)
            manual_prompt = history[0][0].parts[0]
            assert isinstance(manual_prompt.content, list)
            _ = manual_prompt.content.pop(-1)
        else:
            # Note: Raises IndexError if list is empty or index is out of range.
            _ = history.pop(1)
            _ = self.request_tokens.pop(1)
            _ = self.response_tokens.pop(1)

        self.num_times_truncated += 1
        self.message_history = history

    def reset(self) -> None:
        """Reset the usage stats."""
        self.message_history = []
        self.num_requests = 0
        self.request_tokens = []
        self.response_tokens = []
        self.num_times_truncated = 0
