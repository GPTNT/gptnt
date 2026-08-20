from dataclasses import dataclass, field
from typing import Self

from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart

from gptnt.ktane.manuals.artifacts import ManualArtifact
from gptnt.players.conversation._coercion import coerce_tool_output_into_native_output
from gptnt.players.conversation._entry import Entry
from gptnt.players.conversation._observations import (
    partition_non_pinned_by_window,
    remove_binary_content_from_messages,
    remove_binary_content_outside_window,
)
from gptnt.players.conversation._truncation import drop_oldest_non_pinned, turns_to_drop
from gptnt.players.specification import PlayerCapabilities, PlayerProtocol
from gptnt.prompts.manual import load_prepared_manual_as_prompt


@dataclass(kw_only=True)
class Conversation:
    """Store every conversation entry and build the history sent to the model.

    `_dropped_non_pinned` counts the oldest non-pinned entries omitted from every future request.
    That count can increase but cannot decrease. Image eviction removes old image bytes from
    storage; neither truncation nor eviction removes stored text.
    """

    entries: list[Entry] = field(default_factory=list)
    _dropped_non_pinned: int = field(default=0, init=False, repr=False)
    _evaluated_non_pinned: int = field(default=0, init=False, repr=False)

    @classmethod
    def begin(
        cls,
        *,
        capabilities: PlayerCapabilities,
        protocol: PlayerProtocol,
        prior_messages: list[ModelMessage] | None = None,
        manual_artifact: ManualArtifact | None = None,
    ) -> Self:
        """Seed the manual from an artifact, then append any pinned prior-episode messages.

        A manual-bearing protocol requires the prepared artifact selected for its experiment.
        """
        entries: list[Entry] = []

        if protocol.include_manual:
            if manual_artifact:
                manual_parts = load_prepared_manual_as_prompt(
                    manual_artifact, image_dimensions=capabilities.image_dimensions
                )
            else:
                raise RuntimeError("a prepared manual artifact is required for this conversation")
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
        """Append a non-pinned exchange with its measured prompt size."""
        self.entries.append(Entry.from_turn(messages=new_messages))

    def evict_observations(self, window: int) -> None:
        """Drop image bytes from non-pinned entries outside `window`."""
        aged, _ = partition_non_pinned_by_window(self.entries, window=window)
        for index in aged:
            self.entries[index].messages = remove_binary_content_from_messages(
                self.entries[index].messages, keep_last=False
            )

    def render(self, capabilities: PlayerCapabilities) -> list[ModelMessage]:
        """Build the message history for the next model request.

        First update the number of permanently omitted turns. Then remove images outside the
        observation window, convert tool output to the model's native output format, and flatten
        the remaining entries into messages.
        """
        self._refresh_truncation(capabilities)
        kept = drop_oldest_non_pinned(entries=self.entries, count=self._dropped_non_pinned)
        windowed = remove_binary_content_outside_window(
            entries=kept, window=capabilities.preserve_last_frame_for_n_turns
        )
        return [
            message
            for entry in windowed
            for message in coerce_tool_output_into_native_output(entry.messages)
        ]

    def num_entries_dropped(self, capabilities: PlayerCapabilities) -> int:
        """Return how many oldest non-pinned entries the next request omits."""
        self._refresh_truncation(capabilities)
        return self._dropped_non_pinned

    def _refresh_truncation(self, capabilities: PlayerCapabilities) -> None:
        """Update the omitted-entry count after a turn is recorded.

        The latest provider count measured a prompt that already omitted the current prefix. Only
        entries after that prefix may be subtracted from the measurement. The count never
        decreases, so later requests cannot restore previously omitted entries. A zero provider
        count leaves it unchanged.
        """
        non_pinned = sum(not entry.pinned for entry in self.entries)
        if non_pinned == self._evaluated_non_pinned:
            return

        self._dropped_non_pinned = turns_to_drop(
            entries=self.entries,
            input_tokens_limit=capabilities.usage_limits.input_tokens_limit,
            preserve_window=capabilities.preserve_last_frame_for_n_turns,
            tokens_per_image=capabilities.tokens_per_image,
            max_observations_per_request=capabilities.max_observations_per_request,
            omitted_count=self._dropped_non_pinned,
        )
        self._evaluated_non_pinned = non_pinned
