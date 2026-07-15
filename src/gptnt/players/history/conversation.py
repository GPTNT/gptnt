from dataclasses import dataclass, field
from typing import Self

from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart

from gptnt.players.deps import PlayerDeps
from gptnt.players.history._coercion import coerce_tool_output_into_native_output
from gptnt.players.history._entry import Entry
from gptnt.players.history._observations import (
    _evict_binary_content,
    remove_binary_content_outside_window,
)
from gptnt.players.history._truncation import truncate, turns_to_drop
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
    def begin(cls, deps: PlayerDeps, *, prior_messages: list[ModelMessage] | None = None) -> Self:
        """Seed the pinned preamble: the manual when included, then any prior-episode messages."""
        entries: list[Entry] = []
        if deps.protocol.include_manual:
            manual_parts = load_manual_as_prompt(
                image_dimensions=deps.capabilities.image_dimensions
            )
            entries.append(
                Entry(
                    messages=[ModelRequest(parts=[UserPromptPart(content=manual_parts)])],
                    pinned=True,
                )
            )
        if prior_messages:
            entries.append(Entry(messages=list(prior_messages), pinned=True))
        return cls(entries=entries)

    def record(self, new_messages: list[ModelMessage]) -> None:
        """Append one exchange as a non-pinned turn, stamped with its real prompt size."""
        self.entries.append(Entry.from_turn(messages=new_messages))

    def evict_observations(self, window: int) -> None:
        """Drop image bytes from non-pinned entries older than the last `window` turns."""
        non_pinned = [index for index, entry in enumerate(self.entries) if not entry.pinned]
        aged = non_pinned[: max(len(non_pinned) - window, 0)] if window > 0 else non_pinned
        for index in aged:
            self.entries[index].messages = _evict_binary_content(
                self.entries[index].messages, keep_last=False
            )

    def render(self, deps: PlayerDeps) -> list[ModelMessage]:
        """Build the message view the model sees: truncate, then window, then coerce, then flatten.

        Pure query over `self.entries`. The view reuses stored message objects and copies one only
        where windowing or coercion rewrites it.
        """
        return [message for entry in self._shaped(deps) for message in entry.messages]

    def truncated_turn_count(self, deps: PlayerDeps) -> int:
        """Oldest turns truncation drops from the store, recorded as `num_prompt_truncations`."""
        return turns_to_drop(
            entries=self.entries,
            input_tokens_limit=deps.capabilities.usage_limits.input_tokens_limit,
            truncation_forecast_window=deps.capabilities.truncation_forecast_window,
        )

    def _shaped(self, deps: PlayerDeps) -> list[Entry]:
        kept = truncate(self.entries, deps.capabilities)
        windowed = remove_binary_content_outside_window(
            entries=kept, window=deps.capabilities.preserve_last_frame_for_n_turns
        )
        return [
            Entry(
                messages=coerce_tool_output_into_native_output(entry.messages), pinned=entry.pinned
            )
            for entry in windowed
        ]
