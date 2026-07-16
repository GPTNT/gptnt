import math
from dataclasses import dataclass, field
from typing import Self

from pydantic_ai import BinaryContent, ModelMessage, ModelResponse, RequestUsage
from pydantic_ai.messages import ModelRequestPart, ModelResponsePart, UserContent

_CHARS_PER_TOKEN = 4
"""Rough characters-per-token ratio for text (English averages about four)."""


def _text_chars(element: ModelRequestPart | ModelResponsePart | UserContent) -> int:
    """Number of text characters `element` contributes: a message part, or a piece within one."""
    if isinstance(element, str):
        return len(element)
    content = getattr(element, "content", None)
    if isinstance(content, str):
        return len(content)
    args = getattr(element, "args", None)
    return len(str(args)) if args else 0


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
        """The measured prompt tokens for this entry.

        `input_tokens` is already the whole prompt: genai-prices reports the cache and audio
        buckets as sub-counts contained within it, not disjoint additions.
        """
        return self.usage.input_tokens

    def estimated_render_tokens(self, *, in_window: bool, tokens_per_image: int) -> int:
        """Estimate the tokens this entry adds to a render.

        The estimated counterpart of `total_input_tokens`. Text is estimated from its length at a
        fixed characters-per-token ratio rather than a real tokenizer because they're not really
        that huge - we cap max tokens on the running so it should be okay.

        Binary content (images, etc) are the heft of the prompt and we estimate the tokens per each
        using `tokens_per_image`.

        We count images differently depending on whether the entry is pinned, in the observation
        window, or aged out. Pinned entries keep all their images, in-window entries keep one image
        per part, and aged-out entries keep none. This is because the window keeps one image per
        part, and once an entry has aged out, its images are stripped.

        The `in_window` parameter indicates whether the entry is currently in the observation
        window or not.
        """
        text_chars = 0
        image_bearing_parts = 0
        total_images = 0
        for message in self.messages:
            for part in message.parts:
                content = getattr(part, "content", None)
                if isinstance(content, list | tuple):
                    part_images = sum(isinstance(piece, BinaryContent) for piece in content)
                    total_images += part_images
                    image_bearing_parts += part_images > 0
                    text_chars += sum(_text_chars(piece) for piece in content)
                else:
                    text_chars += _text_chars(part)

        if self.pinned:
            images = total_images
        elif in_window:
            images = image_bearing_parts
        else:
            images = 0
        return math.ceil(text_chars / _CHARS_PER_TOKEN) + images * tokens_per_image
