from dataclasses import dataclass, field
from typing import Self

from pydantic_ai import BinaryContent, RequestUsage
from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart

from gptnt.players.conversation._coercion import coerce_tool_output_into_native_output
from gptnt.players.conversation._entry import Entry
from gptnt.players.conversation._observations import (
    remove_binary_content_from_messages,
    remove_binary_content_outside_window,
)
from gptnt.players.conversation._truncation import truncate, turns_to_drop
from gptnt.players.specification import PlayerCapabilities, PlayerProtocol
from gptnt.prompts.manual import load_manual_as_prompt

_CHARS_PER_TOKEN = 4
"""Rough approximation: ~4 characters per token on average."""


@dataclass(kw_only=True)
class Conversation:
    """Append-only store of conversation entries and the render derived from them.

    The store's only mutation is `evict_observations`, which drops image bytes from non-pinned
    entries that have aged out of the observation window. Those bytes are already invisible to
    every current and future render, so eviction changes no render output. Recorded text is never
    touched, and `render` never mutates the store.
    """

    entries: list[Entry] = field(default_factory=list)

    @classmethod
    def begin(
        cls,
        *,
        capabilities: PlayerCapabilities,
        protocol: PlayerProtocol,
        prior_messages: list[ModelMessage] | None = None,
    ) -> Self:
        """Seed the pinned preamble: the manual when included, then any prior-episode messages."""
        entries: list[Entry] = []

        if protocol.include_manual:
            manual_parts = load_manual_as_prompt(image_dimensions=capabilities.image_dimensions)
            num_tokens_for_manual_images = (
                sum(1 for part in manual_parts if isinstance(part, BinaryContent))
                * capabilities.tokens_per_image
            )
            num_tokens_for_manual_text = (
                sum(len(part) for part in manual_parts if isinstance(part, str))
                // _CHARS_PER_TOKEN
            )
            entries.append(
                Entry(
                    messages=[ModelRequest(parts=[UserPromptPart(content=manual_parts)])],
                    pinned=True,
                    usage=RequestUsage(
                        input_tokens=num_tokens_for_manual_images + num_tokens_for_manual_text
                    ),
                )
            )

        if prior_messages:
            entries.append(Entry(messages=prior_messages, pinned=True))

        return cls(entries=entries)

    def record(self, new_messages: list[ModelMessage]) -> None:
        """Append one exchange as a non-pinned turn, stamped with its real prompt size."""
        self.entries.append(Entry.from_turn(messages=new_messages))

    def evict_observations(self, window: int) -> None:
        """Drop image bytes from non-pinned entries older than the last `window` turns."""
        non_pinned = [index for index, entry in enumerate(self.entries) if not entry.pinned]
        # Figure out which entries are outside the window and evict their binary content
        aged = non_pinned[: max(len(non_pinned) - window, 0)] if window > 0 else non_pinned
        for index in aged:
            self.entries[index].messages = remove_binary_content_from_messages(
                self.entries[index].messages, keep_last=False
            )

    def render(self, capabilities: PlayerCapabilities) -> list[ModelMessage]:
        """Build the message view to send to the model.

        This means: truncate, then window, then coerce, then flatten. It's a query over the
        existing entries and doesn't directly mutate them. The returned messages are a copy of the
        originals, with any evicted binary content removed and any tool output coerced into native
        output.
        """
        return [message for entry in self._shaped(capabilities) for message in entry.messages]

    def num_entries_dropped(self, capabilities: PlayerCapabilities) -> int:
        """Compute the number of entries that were dropped from the conversation."""
        return turns_to_drop(
            entries=self.entries,
            input_tokens_limit=capabilities.usage_limits.input_tokens_limit,
            truncation_forecast_window=capabilities.truncation_forecast_window,
        )

    def _shaped(self, capabilities: PlayerCapabilities) -> list[Entry]:
        kept = truncate(
            entries=self.entries,
            input_tokens_limit=capabilities.usage_limits.input_tokens_limit,
            truncation_forecast_window=capabilities.truncation_forecast_window,
        )
        windowed = remove_binary_content_outside_window(
            entries=kept, window=capabilities.preserve_last_frame_for_n_turns
        )
        return [
            Entry(
                messages=coerce_tool_output_into_native_output(entry.messages), pinned=entry.pinned
            )
            for entry in windowed
        ]
