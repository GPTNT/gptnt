from dataclasses import dataclass, field
from typing import Self

from pydantic_ai import ModelMessage, ModelResponse, RequestUsage


@dataclass(kw_only=True)
class Entry:
    """Messages from one exchange, plus whether the entry is pinned.

    Pinned entries hold the manual and any prior-episode context. They are never truncated and keep
    their images through eviction. Non-pinned entries are the conversation turns.
    """

    messages: list[ModelMessage]
    pinned: bool = field(default=False)

    usage: RequestUsage = field(default_factory=RequestUsage)

    @classmethod
    def from_turn(cls, *, messages: list[ModelMessage], pinned: bool = False) -> Self:
        usage = RequestUsage()
        for message in messages:
            if isinstance(message, ModelResponse):
                usage.incr(message.usage)
        return cls(messages=messages, pinned=pinned, usage=usage)

    @property
    def total_input_tokens(self) -> int:
        """The total input tokens for this entry."""
        return (
            self.usage.input_tokens
            + self.usage.cache_read_tokens
            + self.usage.cache_write_tokens
            + self.usage.cache_audio_read_tokens
        )

    def add_to_input_tokens(self, additional_tokens: int) -> None:
        """Add to the total input tokens for this entry.

        This is used when we have to add additional tokens to the entry that are not accounted for
        in the messages themselves. This is expected behaviour because we can't do anything about
        it.
        """
        self.usage.input_tokens += additional_tokens
