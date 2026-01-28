"""Tests for TokenAccountant."""

import pytest
from pydantic_ai import RunUsage, UsageLimits

from gptnt.players.ai.messages.token_accountant import TokenAccountant
from gptnt.players.specification import PlayerCapabilities, PlayerProtocol


@pytest.fixture
def defuser_protocol() -> PlayerProtocol:
    """Create a defuser protocol."""
    return PlayerProtocol(
        role="defuser", include_manual=False, is_playing_alone=True, communication_style="async"
    )


@pytest.fixture
def expert_protocol() -> PlayerProtocol:
    """Create an expert protocol."""
    return PlayerProtocol(
        role="expert", include_manual=False, is_playing_alone=False, communication_style="sync"
    )


@pytest.fixture
def capabilities_with_limit() -> PlayerCapabilities:
    """Create capabilities with a token limit."""
    return PlayerCapabilities(
        player_name="gpt4o-mini",
        player_type="ai",
        max_observations_per_request=3,
        preserve_last_frame_for_n_turns=1,
        structured_output_mode="prompted",
        usage_limits=UsageLimits(input_tokens_limit=10000),
    )


@pytest.fixture
def capabilities_no_limit() -> PlayerCapabilities:
    """Create capabilities without a token limit."""
    return PlayerCapabilities(
        player_name="gpt4o-mini",
        player_type="ai",
        max_observations_per_request=3,
        preserve_last_frame_for_n_turns=1,
        structured_output_mode="prompted",
        usage_limits=UsageLimits(input_tokens_limit=None),
    )


@pytest.fixture
def token_accountant(
    defuser_protocol: PlayerProtocol, capabilities_with_limit: PlayerCapabilities
) -> TokenAccountant:
    """Create a token accountant."""
    return TokenAccountant(
        capabilities=capabilities_with_limit, protocol=defuser_protocol, usage=RunUsage()
    )


class TestTokensPerImage:
    """Test tokens_per_image property."""

    def test_tokens_per_image_gpt4o(
        self, defuser_protocol: PlayerProtocol, capabilities_with_limit: PlayerCapabilities
    ) -> None:
        """Test that tokens_per_image returns correct value for gpt4o models."""
        accountant = TokenAccountant(
            capabilities=capabilities_with_limit, protocol=defuser_protocol, usage=RunUsage()
        )
        # gpt4o-mini should return 85 tokens per image
        assert accountant.tokens_per_image == 85


class TestDeductObservationTokens:
    """Test deduct_observation_tokens method."""

    def test_deduct_tokens_normal_case(self, token_accountant: TokenAccountant) -> None:
        """Test deducting tokens in normal case."""
        token_accountant.usage.input_tokens = 1000

        deducted = token_accountant.deduct_observation_tokens(3)

        # 3 observations * 85 tokens = 255 tokens
        assert deducted == 255
        assert token_accountant.usage.input_tokens == 1000 - 255

    def test_deduct_tokens_zero_observations(self, token_accountant: TokenAccountant) -> None:
        """Test deducting zero observations."""
        token_accountant.usage.input_tokens = 1000

        deducted = token_accountant.deduct_observation_tokens(0)

        assert deducted == 0
        assert token_accountant.usage.input_tokens == 1000

    def test_deduct_tokens_negative_observations(self, token_accountant: TokenAccountant) -> None:
        """Test deducting negative observations."""
        token_accountant.usage.input_tokens = 1000

        deducted = token_accountant.deduct_observation_tokens(-1)

        assert deducted == 0
        assert token_accountant.usage.input_tokens == 1000

    def test_deduct_tokens_would_go_negative(self, token_accountant: TokenAccountant) -> None:
        """Test deducting more tokens than available (should clamp to 0)."""
        token_accountant.usage.input_tokens = 100

        # Try to deduct 3 observations * 85 = 255 tokens when only 100 available
        deducted = token_accountant.deduct_observation_tokens(3)

        # Should clamp to 0 and return actual amount deducted
        assert token_accountant.usage.input_tokens == 0
        assert deducted == 100

    def test_deduct_tokens_with_zero_usage(self, token_accountant: TokenAccountant) -> None:
        """Test deducting tokens when usage is already 0."""
        token_accountant.usage.input_tokens = 0

        deducted = token_accountant.deduct_observation_tokens(3)

        assert deducted == 0
        assert token_accountant.usage.input_tokens == 0


class TestDeductObservationTokensFromRun:
    """Test deduct_observation_tokens_from_run method."""

    def test_deduct_from_run_normal_case(self, token_accountant: TokenAccountant) -> None:
        """Test deducting tokens from both usage and run."""
        token_accountant.usage.input_tokens = 1000
        run_tokens = 500

        usage_deducted, new_run_tokens = token_accountant.deduct_observation_tokens_from_run(
            3, run_tokens
        )

        # 3 observations * 85 tokens = 255 tokens
        assert usage_deducted == 255
        assert new_run_tokens == 500 - 255
        assert token_accountant.usage.input_tokens == 1000 - 255

    def test_deduct_from_run_zero_observations(self, token_accountant: TokenAccountant) -> None:
        """Test deducting zero observations from run."""
        token_accountant.usage.input_tokens = 1000
        run_tokens = 500

        usage_deducted, new_run_tokens = token_accountant.deduct_observation_tokens_from_run(
            0, run_tokens
        )

        assert usage_deducted == 0
        assert new_run_tokens == 500
        assert token_accountant.usage.input_tokens == 1000

    def test_deduct_from_run_would_go_negative(self, token_accountant: TokenAccountant) -> None:
        """Test deducting tokens from run that would go negative."""
        token_accountant.usage.input_tokens = 1000
        run_tokens = 100

        # Try to deduct 3 observations * 85 = 255 tokens from run with only 100 tokens
        _usage_deducted, new_run_tokens = token_accountant.deduct_observation_tokens_from_run(
            3, run_tokens
        )

        # Usage should be deducted normally
        assert token_accountant.usage.input_tokens == 1000 - 255
        # But run tokens should clamp to 0
        assert new_run_tokens == 0

    def test_deduct_from_run_both_would_go_negative(
        self, token_accountant: TokenAccountant
    ) -> None:
        """Test deducting tokens when both usage and run would go negative."""
        token_accountant.usage.input_tokens = 100
        run_tokens = 50

        _usage_deducted, new_run_tokens = token_accountant.deduct_observation_tokens_from_run(
            3, run_tokens
        )

        # Both should clamp to 0
        assert token_accountant.usage.input_tokens == 0
        assert new_run_tokens == 0


class TestEstimateNextRunTokens:
    """Test estimate_next_run_tokens method."""

    def test_estimate_defuser_no_message(
        self, defuser_protocol: PlayerProtocol, capabilities_with_limit: PlayerCapabilities
    ) -> None:
        """Test estimation for defuser without next message."""
        accountant = TokenAccountant(
            capabilities=capabilities_with_limit,
            protocol=defuser_protocol,
            usage=RunUsage(input_tokens=1000, output_tokens=200),
        )

        estimated = accountant.estimate_next_run_tokens()

        # Should include total_tokens (1200) + images (3 * 85 = 255)
        assert estimated == 1200 + 255

    def test_estimate_defuser_with_message(
        self, defuser_protocol: PlayerProtocol, capabilities_with_limit: PlayerCapabilities
    ) -> None:
        """Test estimation for defuser with next message."""
        accountant = TokenAccountant(
            capabilities=capabilities_with_limit,
            protocol=defuser_protocol,
            usage=RunUsage(input_tokens=1000, output_tokens=200),
        )

        estimated = accountant.estimate_next_run_tokens(next_message="Hello world")

        # Should include total_tokens (1200) + images (255) + message tokens
        # "Hello world" is ~2-3 tokens, let's verify it's > base
        assert estimated > 1200 + 255

    def test_estimate_expert_no_images(
        self, expert_protocol: PlayerProtocol, capabilities_with_limit: PlayerCapabilities
    ) -> None:
        """Test estimation for expert (no images)."""
        accountant = TokenAccountant(
            capabilities=capabilities_with_limit,
            protocol=expert_protocol,
            usage=RunUsage(input_tokens=1000, output_tokens=200),
        )

        estimated = accountant.estimate_next_run_tokens()

        # Should only include total_tokens, no images
        assert estimated == 1200

    def test_estimate_with_zero_usage(self, token_accountant: TokenAccountant) -> None:
        """Test estimation with zero usage."""
        estimated = token_accountant.estimate_next_run_tokens()

        # Should only include images (3 * 85 = 255)
        assert estimated == 255


class TestShouldTruncate:
    """Test should_truncate method."""

    def test_should_truncate_below_threshold(self, token_accountant: TokenAccountant) -> None:
        """Test that truncation is not triggered below threshold."""
        token_accountant.usage.input_tokens = 5000  # 50% of 10000 limit

        # Should not truncate at 90% threshold
        assert not token_accountant.should_truncate(threshold=0.9)

    def test_should_truncate_above_threshold(self, token_accountant: TokenAccountant) -> None:
        """Test that truncation is triggered above threshold."""
        token_accountant.usage.input_tokens = 9500  # 95% of 10000 limit

        # Should truncate at 90% threshold (including images pushes over)
        assert token_accountant.should_truncate(threshold=0.9)

    def test_should_truncate_no_limit(
        self, defuser_protocol: PlayerProtocol, capabilities_no_limit: PlayerCapabilities
    ) -> None:
        """Test that truncation never happens with no limit."""
        accountant = TokenAccountant(
            capabilities=capabilities_no_limit,
            protocol=defuser_protocol,
            usage=RunUsage(input_tokens=999999),
        )

        # Should never truncate regardless of usage
        assert not accountant.should_truncate(threshold=0.9)

    def test_should_truncate_at_exact_threshold(self, token_accountant: TokenAccountant) -> None:
        """Test truncation at exactly the threshold."""
        # Set usage to exactly 90% of limit minus images
        # 10000 * 0.9 = 9000, minus 255 for images = 8745
        token_accountant.usage.input_tokens = 8745

        # Should not truncate (we use > not >=)
        assert not token_accountant.should_truncate(threshold=0.9)

    def test_should_truncate_with_next_message(self, token_accountant: TokenAccountant) -> None:
        """Test truncation with next message included."""
        token_accountant.usage.input_tokens = 8700

        # Without message, might not truncate
        # With a long message, should push over threshold
        long_message = "word " * 1000  # ~1000+ tokens

        assert token_accountant.should_truncate(threshold=0.9, next_message=long_message)


def test_deduct_run_tokens(token_accountant: TokenAccountant) -> None:
    """Test deducting tokens from a removed run."""
    token_accountant.usage.input_tokens = 2000

    # Deduct run with 500 input + 100 output
    token_accountant.deduct_run_tokens(input_tokens=500, output_tokens=100)

    # Both should be subtracted from input_tokens (context length)
    assert token_accountant.usage.input_tokens == 2000 - 500 - 100
