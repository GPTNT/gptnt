from dataclasses import dataclass, field

import structlog
from pydantic_ai import RunUsage, UsageLimits

from gptnt.core.players.tokens import count_tokens_from_text, estimate_tokens_for_image_per_model
from gptnt.core.specification import PlayerCapabilities, PlayerProtocol

logger = structlog.get_logger()


@dataclass(kw_only=True)
class TokenAccountant:
    """Single source of truth for token accounting.

    Every mutation of `self.usage` goes through one of the four public mutators below. Nothing
    outside this class should touch `self.usage` directly.

    Mutators (in the order they're typically called during a step):
        1. `add_initial_tokens` - seed with manual-prompt tokens (once)
        2. `record_model_response` - replace cumulative usage after an LLM call
        3. `deduct_observations` - remove observation tokens from usage and return the adjusted
            per-run input-token count
        4. `deduct_run` - remove a whole run's worth of tokens (truncation)
    """

    capabilities: PlayerCapabilities
    protocol: PlayerProtocol
    usage: RunUsage = field(default_factory=RunUsage)

    @property
    def tokens_per_image(self) -> int:
        """Estimated tokens for one image on the current model."""
        return estimate_tokens_for_image_per_model(
            model=self.capabilities.player_name,
            long_side=self.capabilities.image_dimensions.long_side,
            short_side=self.capabilities.image_dimensions.short_side,
        )

    @property
    def usage_limits(self) -> UsageLimits:
        """Usage limits configured for the player."""
        return self.capabilities.usage_limits

    def add_initial_tokens(self, tokens: int) -> None:
        """Seed usage with tokens that exist before any model call (e.g. manual).

        Must be called *before* the first `record_model_response`.
        """
        self.usage.input_tokens += tokens

    def record_model_response(self, usage: RunUsage) -> tuple[int, int]:
        """Record a model response and compute per-run token deltas.

        The delta is computed against the current cumulative total so that earlier deductions
        (which keep the baseline aligned with what the model actually sees) are naturally accounted
        for.

        Returns:
            `(input_tokens_for_run, output_tokens_for_run)`
        """
        input_tokens_for_run = max(usage.input_tokens - self.usage.total_tokens, 0)
        output_tokens_for_run = usage.output_tokens
        self.usage = usage
        return input_tokens_for_run, output_tokens_for_run

    def deduct_observations(self, num_observations: int, *, run_input_tokens: int) -> int:
        """Deduct observation (image) tokens from cumulative usage and a run.

        All clamping is handled internally so callers don't need to worry about negative values.

        Args:
            num_observations: Number of observations being removed.
            run_input_tokens: The per-run input token count to adjust.

        Returns:
            The adjusted `run_input_tokens` after deduction.
        """
        if num_observations <= 0:
            return run_input_tokens

        token_cost = num_observations * self.tokens_per_image

        # deduct from cumulative usage
        _ = self._clamped_deduct(token_cost, label="observation")

        # deduct from the run's own count
        run_deduction = min(token_cost, run_input_tokens)
        return max(run_input_tokens - run_deduction, 0)

    def deduct_run(self, *, input_tokens: int, output_tokens: int) -> None:
        """Deduct a whole run's tokens from cumulative usage (truncation).

        Both input and output count toward context length, so both are subtracted from
        `usage.input_tokens`.  Result is clamped to zero.
        """
        total = input_tokens + output_tokens
        if total <= 0:
            return
        _ = self._clamped_deduct(total, label="run")

    def estimate_next_run_tokens(self, *, next_message: str | None = None) -> int:
        """Estimate input tokens the model will see on the next call.

        Includes current cumulative total, expected images (defuser only), and an optional
        forthcoming text message.
        """
        model_input = self.usage.total_tokens or 0

        if self.protocol.role == "defuser":
            model_input += self.tokens_per_image * self.capabilities.max_observations_per_request

        if next_message:
            model_input += count_tokens_from_text(next_message)

        return model_input

    def should_truncate(self, *, threshold: float, next_message: str | None = None) -> bool:
        """Check whether estimated usage exceeds `threshold * limit`."""
        if self.capabilities.usage_limits.input_tokens_limit is None:
            return False

        estimated_input = self.estimate_next_run_tokens(next_message=next_message)
        return estimated_input > (self.capabilities.usage_limits.input_tokens_limit * threshold)

    def _clamped_deduct(self, amount: int, *, label: str) -> int:
        """Subtract amount from `usage.input_tokens`, clamping to zero.

        Returns the number of tokens actually deducted.
        """
        if amount <= 0 or self.usage.input_tokens <= 0:
            return 0

        actually_deducted = min(amount, self.usage.input_tokens)
        new_value = self.usage.input_tokens - actually_deducted

        if new_value < 0:  # unneeded because min() above should prevent this, but i've seen things
            logger.warning(
                f"{label.capitalize()} token deduction would go negative: "
                f"{self.usage.input_tokens=} - {amount=} -> clamping to 0"
            )
            new_value = 0

        self.usage.input_tokens = new_value
        return actually_deducted
