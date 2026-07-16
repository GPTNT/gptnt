from dataclasses import dataclass, field
from typing import Self

from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart

from gptnt.players.conversation._coercion import coerce_tool_output_into_native_output
from gptnt.players.conversation._entry import Entry
from gptnt.players.conversation._observations import (
    partition_non_pinned_by_window,
    remove_binary_content_from_messages,
    remove_binary_content_outside_window,
)
from gptnt.players.conversation._truncation import truncate, turns_to_drop
from gptnt.players.specification import PlayerCapabilities, PlayerProtocol
from gptnt.prompts.manual import load_manual_as_prompt


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
            entries.append(
                Entry(
                    messages=[ModelRequest(parts=[UserPromptPart(content=manual_parts)])],
                    pinned=True,
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
        aged, _ = partition_non_pinned_by_window(self.entries, window=window)
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
        kept = truncate(
            entries=self.entries,
            input_tokens_limit=capabilities.usage_limits.input_tokens_limit,
            preserve_window=capabilities.preserve_last_frame_for_n_turns,
            tokens_per_image=capabilities.tokens_per_image,
            max_observations_per_request=capabilities.max_observations_per_request,
        )
        windowed = remove_binary_content_outside_window(
            entries=kept, window=capabilities.preserve_last_frame_for_n_turns
        )
        coerced = (
            Entry(
                messages=coerce_tool_output_into_native_output(entry.messages), pinned=entry.pinned
            )
            for entry in windowed
        )
        return [message for entry in coerced for message in entry.messages]

    def num_entries_dropped(self, capabilities: PlayerCapabilities) -> int:
        """Compute the number of entries that were dropped from the conversation."""
        return turns_to_drop(
            entries=self.entries,
            input_tokens_limit=capabilities.usage_limits.input_tokens_limit,
            preserve_window=capabilities.preserve_last_frame_for_n_turns,
            tokens_per_image=capabilities.tokens_per_image,
            max_observations_per_request=capabilities.max_observations_per_request,
        )
