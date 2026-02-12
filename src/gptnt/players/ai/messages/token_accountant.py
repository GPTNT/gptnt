from dataclasses import dataclass, field

import structlog
from pydantic_ai import RunUsage, UsageLimits

from gptnt.ktane.game_settings import KtaneSettings
from gptnt.players.ai.tokens import count_tokens_from_text, estimate_tokens_for_image_per_model
from gptnt.players.specification import PlayerCapabilities, PlayerProtocol

logger = structlog.get_logger()


@dataclass(kw_only=True)
class TokenAccountant:
    """Manages token accounting and estimation for message history.

    This class centralizes all token-related calculations, including:
        - Tracking cumulative usage via RunUsage
        - Estimating tokens for observations (images)
        - Correcting token counts when observations are removed
        - Determining if truncation is needed based on usage limits
    """

    capabilities: PlayerCapabilities
    protocol: PlayerProtocol
    usage: RunUsage = field(default_factory=RunUsage)

    @property
    def tokens_per_image(self) -> int:
        """Estimate the number of tokens per image for the current model."""
        ktane_settings = KtaneSettings()
        return estimate_tokens_for_image_per_model(
            model=self.capabilities.player_name,
            long_side=ktane_settings.game_width,
            short_side=ktane_settings.game_height,
        )

    @property
    def usage_limits(self) -> UsageLimits:
        """Get the usage limits from capabilities."""
        return self.capabilities.usage_limits

    def deduct_observation_tokens(self, num_observations: int) -> int:
        """Deduct tokens for removed observations from usage.

        Args:
            num_observations: Number of observations being removed

        Returns:
            The number of tokens actually deducted (may be clamped to prevent negatives)
        """
        if num_observations <= 0 or self.usage.input_tokens <= 0:
            return 0

        tokens_to_remove = min(num_observations * self.tokens_per_image, self.usage.input_tokens)
        new_usage_input_tokens = self.usage.input_tokens - tokens_to_remove

        if new_usage_input_tokens < 0:
            logger.warning(
                f"Token correction would go negative: {self.usage.input_tokens=} "
                f"- {tokens_to_remove=} -> clamping to 0"
            )
            new_usage_input_tokens = 0

        self.usage.input_tokens = new_usage_input_tokens
        return tokens_to_remove

    def deduct_observation_tokens_from_run(
        self, num_observations: int, run_input_tokens: int
    ) -> tuple[int, int]:
        """Deduct observation tokens from both usage and a specific run's token count.

        Args:
            num_observations: Number of observations being removed
            run_input_tokens: The input token count for the specific run

        Returns:
            Tuple of (tokens_deducted_from_usage, new_run_input_tokens)
        """
        tokens_deducted_from_usage = self.deduct_observation_tokens(num_observations)

        if num_observations <= 0:
            return 0, run_input_tokens

        tokens_to_remove = num_observations * self.tokens_per_image
        new_run_input_tokens = run_input_tokens - tokens_to_remove

        if new_run_input_tokens < 0:
            logger.warning(
                f"Token correction for run would go negative: {run_input_tokens=} "
                f"- {tokens_to_remove=} -> clamping to 0"
            )
            new_run_input_tokens = 0

        return tokens_deducted_from_usage, new_run_input_tokens

    def estimate_next_run_tokens(self, *, next_message: str | None = None) -> int:
        """Calculate the estimated input tokens for the next run.

        This includes:
        - Current cumulative usage (total_tokens)
        - Tokens for images if defuser role (max_observations_per_request)
        - Tokens for the next message if provided

        Args:
            next_message: Optional message to include in estimation

        Returns:
            Estimated total input tokens for next run
        """
        model_input = self.usage.total_tokens or 0

        # If we are a defuser, then we need to add in the tokens for the images we would send,
        # which we estimate using the maximum number of observations per request
        if self.protocol.role == "defuser":
            model_input += self.tokens_per_image * self.capabilities.max_observations_per_request

        # Also add in the tokens for the next message if we have one
        if next_message:
            model_input += count_tokens_from_text(next_message)

        return model_input

    def should_truncate(self, *, threshold: float, next_message: str | None = None) -> bool:
        """Check if message history should be truncated based on usage limits.

        Args:
            threshold: Fraction of limit at which to trigger truncation (e.g., 0.9 for 90%)
            next_message: Optional message to include in estimation

        Returns:
            True if estimated usage exceeds threshold * limit
        """
        if self.capabilities.usage_limits.input_tokens_limit is None:
            # If there is no limit, we never truncate
            return False

        estimated_input = self.estimate_next_run_tokens(next_message=next_message)

        # Check if we are over the context length
        return estimated_input > (self.capabilities.usage_limits.input_tokens_limit * threshold)

    def deduct_run_tokens(self, *, input_tokens: int, output_tokens: int) -> None:
        """Deduct tokens from a removed run during truncation.

        We need to subtract both from the input tokens because they both count toward the context
        length.
        """
        self.usage.input_tokens -= input_tokens
        self.usage.input_tokens -= output_tokens
