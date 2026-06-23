from collections.abc import Callable
from dataclasses import dataclass

import logfire
import structlog

from gptnt.players.history.single_run import SingleRun
from gptnt.players.history.token_accountant import TokenAccountant

logger = structlog.get_logger()


@dataclass(kw_only=True)
class TruncationPolicy:
    """Policy for truncating message history when it exceeds token limits."""

    token_accountant: TokenAccountant
    """Token accountant for checking limits and estimating tokens."""

    threshold: float
    """Truncation threshold (e.g., 0.9 means truncate at 90% of limit)."""

    def should_truncate(
        self, *, turn_runs: list[SingleRun], next_message: str | None = None
    ) -> bool:
        """Check if history should be truncated."""
        # No limit means no truncation
        if self.token_accountant.usage_limits.input_tokens_limit is None:
            return False

        # No turns to truncate
        if not turn_runs:
            return False

        return self.token_accountant.should_truncate(
            threshold=self.threshold, next_message=next_message
        )

    def truncate_history(
        self,
        *,
        turn_runs: list[SingleRun],
        on_truncate_callback: Callable[[SingleRun], None] | None = None,
    ) -> list[SingleRun]:
        """Truncate history until it fits within limits.

        Args:
            turn_runs: List of turn runs to potentially truncate
            on_truncate_callback: Optional callback when a run is removed

        Returns:
            Updated list of turn runs after truncation
        """
        if not self.should_truncate(turn_runs=turn_runs):
            return turn_runs

        with logfire.span("Truncate history"):
            updated_turns = list(turn_runs)

            while self.should_truncate(turn_runs=updated_turns):
                # Remove the first one or break out the loop
                try:
                    run_to_remove = updated_turns[0]
                except IndexError:
                    break

                # Remove from the beginning (oldest turn)
                _ = updated_turns.pop(0)

                # Execute callback if provided
                if on_truncate_callback:
                    on_truncate_callback(run_to_remove)

                logger.info(
                    "Truncated earliest turn from history",
                    removed_run_idx=run_to_remove.idx,
                    remaining_turns=len(updated_turns),
                )

        return updated_turns
