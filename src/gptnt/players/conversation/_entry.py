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
        """The total prompt tokens for this entry.

        `input_tokens` is already the whole prompt: genai-prices reports the cache and audio
        buckets as sub-counts contained within it, not disjoint additions, so summing them on top
        double-counts the cached tokens and inflates the size (badly, on cache-heavy providers).
        """
        return self.usage.input_tokens
