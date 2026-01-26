from dataclasses import dataclass, field

import structlog
from pydantic_ai import BinaryContent, RunUsage
from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart

from gptnt.players.ai.messages.message_transformer import (
    coerce_tool_output_into_native_output,
    ensure_messages_have_valid_final_response,
)
from gptnt.players.ai.messages.observation_window_manager import ObservationWindowManager
from gptnt.players.ai.messages.single_run import SingleRun
from gptnt.players.ai.messages.token_accountant import TokenAccountant
from gptnt.players.ai.messages.truncation_policy import TruncationPolicy
from gptnt.players.ai.tokens import count_tokens_from_text
from gptnt.players.specification import PlayerCapabilities, PlayerProtocol
from gptnt.prompts.manual import load_manual_as_prompt

logger = structlog.get_logger()


@dataclass(kw_only=True)
class MessageHistory:
    """Hold and manage the message history for the AI player."""

    capabilities: PlayerCapabilities
    protocol: PlayerProtocol

    manual_run: SingleRun | None = None
    """Manual as a separate run, if included."""

    turn_runs: list[SingleRun] = field(default_factory=list)
    """Message history of actual conversation turns."""

    num_times_truncated: int = 0
    """Number of times the message history has been truncated."""

    truncation_threshold: float = 0.9
    """Threshold for truncation of the message history."""

    force_convert_tool_output_to_native: bool = True
    """Whether to force convert tool output into native output."""

    token_accountant: TokenAccountant = field(init=False)
    """Manages token accounting and estimation."""

    observation_window_manager: ObservationWindowManager = field(init=False)
    """Manages observation window cleanup."""

    truncation_policy: TruncationPolicy = field(init=False)
    """Policy for truncating history when over token limits."""

    def __post_init__(self) -> None:
        """Post init steps."""
        self.token_accountant = TokenAccountant(
            capabilities=self.capabilities, protocol=self.protocol
        )
        self.observation_window_manager = ObservationWindowManager(
            window_length=self.capabilities.preserve_last_frame_for_n_turns,
            token_accountant=self.token_accountant,
        )
        self.truncation_policy = TruncationPolicy(
            token_accountant=self.token_accountant, threshold=self.truncation_threshold
        )
        if self.protocol.include_manual:
            logger.info("Add the manual into the message history")
            self._build_manual_as_request()

    def __bool__(self) -> bool:
        """Check if the player has any messages."""
        return bool(self.turn_runs) or self.manual_run is not None

    def __len__(self) -> int:
        """Get the number of messages in the history (manual + turns)."""
        num_runs = len(self.turn_runs)
        if self.manual_run:
            num_runs += 1
        return num_runs

    @property
    def usage(self) -> RunUsage:
        """Usage statistics for the latest run."""
        return self.token_accountant.usage

    @property
    def is_empty(self) -> bool:
        """Check if the message history is empty (no manual and no turns)."""
        return self.manual_run is None and len(self.turn_runs) == 0

    @property
    def messages_per_run(self) -> list[SingleRun]:
        """Get all runs (manual + turns) as a combined list.

        This property exists for backwards compatibility with test code.
        """
        if self.manual_run is None:
            return self.turn_runs
        return [self.manual_run, *self.turn_runs]

    def next_run_idx(self) -> int:
        """Get the next run index.

        If manual is present, it's always idx 0, so turn runs start at idx 1. Otherwise, turn runs
        start at idx 0.
        """
        if not self.turn_runs:
            return 1 if self.manual_run else 0
        return max(run.idx for run in self.turn_runs) + 1

    def to_history(self) -> list[ModelMessage]:
        """Get the message history, composing manual + turns."""
        messages = []
        if self.manual_run:
            messages.extend(self.manual_run.messages)
        messages.extend(message for run in self.turn_runs for message in run.messages)
        return messages

    def update(self, *, new_messages: list[ModelMessage], usage: RunUsage) -> None:
        """Update the message history given the player spec.

        This will modify the message history in place. The default behaviour is to do nothing, and
        only modify it by removing things.

        Importantly, since we including the manual in the message history, it will never be
        included in `new_messages`. I checked this manually. So this means we shouldn't need to do
        all the 1000s of checks for it.
        """
        # Track the input and output tokens for this run
        input_tokens_for_run = usage.input_tokens - self.usage.total_tokens
        assert input_tokens_for_run > 0, (
            f"Input tokens for run cannot be negative: {usage.input_tokens=} "
            f"- {self.usage.total_tokens=} -> {input_tokens_for_run}"
        )
        # Note: output tokens is not computed with a delta because the model only outputs once per
        # run
        output_tokens_for_run = usage.output_tokens

        # Update usage BEFORE modifying the messages
        self.token_accountant.usage = usage

        if self.force_convert_tool_output_to_native:
            new_messages = coerce_tool_output_into_native_output(new_messages)

        new_messages = ensure_messages_have_valid_final_response(new_messages)

        if self.protocol.role == "defuser":
            new_messages, num_obs_removed = (
                self.observation_window_manager.remove_observations_from_messages(
                    new_messages,
                    keep_last_observation=self.capabilities.preserve_last_frame_for_n_turns > 0,
                )
            )

            # Update the usage to reflect the number of observation tokens removed
            if num_obs_removed > 0:
                _, input_tokens_for_run = self.token_accountant.deduct_observation_tokens_from_run(
                    num_obs_removed, input_tokens_for_run
                )

        self.turn_runs.append(
            SingleRun(
                messages=new_messages,
                idx=self.next_run_idx(),
                contains_manual=False,  # Turns never contain manual
                input_tokens=input_tokens_for_run,
                output_tokens=output_tokens_for_run,
            )
        )

    def truncate_history_if_needed(self) -> None:
        """Truncate the message history to fit within the usage limits."""
        # Delegate truncation to the policy with callback for bookkeeping
        self.turn_runs = self.truncation_policy.truncate_history(
            turn_runs=self.turn_runs, on_truncate_callback=self._on_run_truncated
        )

    def remove_observations_from_previous_messages(self) -> None:
        """Remove observations from all previous messages in the history.

        Now that we have sent and received the next observation from the model, we want to make
        sure that we only keep the observations for the latest n turns (as per the capabilities).
        Once we receive a new set of messages that has an observation in it, then we can remove
        observations from outside of our observation window.

        Additionally, we make sure that we don't update the run with the manual in it.
        """
        observation_window_length = self.capabilities.preserve_last_frame_for_n_turns

        # We don't need to do anything if we are not the defuser, nor if we don't have enough
        # messages to be truncating with
        if self.protocol.role != "defuser" or len(self.turn_runs) <= observation_window_length:
            return

        self.turn_runs = self.observation_window_manager.apply_window_to_runs(self.turn_runs)

    def _on_run_truncated(self, run: SingleRun) -> None:
        """Callback when a run is truncated - updates usage and counters."""
        # Update the usage - subtract both input and output tokens
        self.token_accountant.deduct_run_tokens(
            input_tokens=run.input_tokens, output_tokens=run.output_tokens
        )
        self.num_times_truncated += 1

    def _build_manual_as_request(self) -> None:
        """Build the manual as a separate run."""
        manual_prompt_parts = load_manual_as_prompt(
            image_dimensions=self.capabilities.image_dimensions
        )
        manual_request = ModelRequest(parts=[UserPromptPart(content=manual_prompt_parts)])
        text_token_estimate = sum(
            count_tokens_from_text(part) for part in manual_prompt_parts if isinstance(part, str)
        )
        image_token_estimate = sum(
            self.token_accountant.tokens_per_image
            for part in manual_prompt_parts
            if isinstance(part, BinaryContent)
        )
        self.manual_run = SingleRun(
            messages=[manual_request],
            idx=0,  # Manual is always idx 0
            contains_manual=True,
            input_tokens=text_token_estimate + image_token_estimate,
            output_tokens=0,
        )
        self.usage.input_tokens += text_token_estimate + image_token_estimate
