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
        player_name="gpt-5",
        player_type="ai",
        max_observations_per_request=3,
        preserve_last_frame_for_n_turns=1,
        structured_output_mode="prompted",
        usage_limits=UsageLimits(input_tokens_limit=100000),
    )


@pytest.fixture
def capabilities_no_limit() -> PlayerCapabilities:
    """Create capabilities without a token limit."""
    return PlayerCapabilities(
        player_name="gpt-5",
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


class TestAddInitialTokens:
    """Test add_initial_tokens method."""

    def test_adds_to_usage(self, token_accountant: TokenAccountant) -> None:
        """Initial tokens are added to usage.input_tokens."""
        token_accountant.add_initial_tokens(1500)
        assert token_accountant.usage.input_tokens == 1500

    def test_cumulative(self, token_accountant: TokenAccountant) -> None:
        """Multiple calls accumulate."""
        token_accountant.add_initial_tokens(1000)
        token_accountant.add_initial_tokens(500)
        assert token_accountant.usage.input_tokens == 1500


class TestRecordModelResponse:
    """Test record_model_response method."""

    def test_first_response(self, token_accountant: TokenAccountant) -> None:
        """First response delta equals the full reported input tokens."""
        usage = RunUsage(input_tokens=5000, output_tokens=200)
        input_delta, output_delta = token_accountant.record_model_response(usage)

        assert input_delta == 5000
        assert output_delta == 200
        assert token_accountant.usage is usage

    def test_subsequent_response(self, token_accountant: TokenAccountant) -> None:
        """Subsequent responses compute delta from previous cumulative total."""
        _ = token_accountant.record_model_response(RunUsage(input_tokens=5000, output_tokens=200))

        input_delta, output_delta = token_accountant.record_model_response(
            RunUsage(input_tokens=10000, output_tokens=300)
        )

        # input delta = 10000 - (5000 + 200) = 4800
        assert input_delta == 4800
        assert output_delta == 300

    def test_delta_after_observation_deduction(self, token_accountant: TokenAccountant) -> None:
        """Observation deductions correctly lower the baseline for the next delta.

        We remove observations from history before the next model call, so the model sees fewer
        tokens and reports a lower cumulative.
        """
        _ = token_accountant.record_model_response(RunUsage(input_tokens=5000, output_tokens=200))
        _ = token_accountant.deduct_observations(3, run_input_tokens=0)

        # Baseline is now (5000 - obs_deducted) + 200
        obs_cost = 3 * token_accountant.tokens_per_image
        baseline = (5000 - obs_cost) + 200

        # Model sees the reduced context + new turn (say 4000 new tokens)
        new_turn_cost = 4000
        next_usage = RunUsage(input_tokens=baseline + new_turn_cost, output_tokens=150)
        input_delta, _ = token_accountant.record_model_response(next_usage)

        assert input_delta == new_turn_cost

    def test_delta_clamps_to_zero(self, token_accountant: TokenAccountant) -> None:
        """If model reports fewer tokens, delta clamps to 0."""
        _ = token_accountant.record_model_response(RunUsage(input_tokens=5000, output_tokens=200))
        input_delta, _ = token_accountant.record_model_response(
            RunUsage(input_tokens=3000, output_tokens=100)
        )
        assert input_delta == 0

    def test_with_initial_tokens(self, token_accountant: TokenAccountant) -> None:
        """Initial tokens (manual) are included in the baseline."""
        token_accountant.add_initial_tokens(1000)

        usage = RunUsage(input_tokens=6000, output_tokens=200)
        input_delta, _ = token_accountant.record_model_response(usage)

        # 6000 - 1000 (initial) = 5000
        assert input_delta == 5000


class TestDeductObservations:
    """Test deduct_observations."""

    def test_normal(self, token_accountant: TokenAccountant) -> None:
        """Both global and run are deducted normally."""
        token_accountant.usage.input_tokens = 10000

        new_run = token_accountant.deduct_observations(3, run_input_tokens=2000)

        expected = 3 * token_accountant.tokens_per_image
        assert new_run == 2000 - expected
        assert token_accountant.usage.input_tokens == 10000 - expected

    def test_zero_observations(self, token_accountant: TokenAccountant) -> None:
        """Zero observations - run tokens returned unchanged."""
        token_accountant.usage.input_tokens = 10000

        new_run = token_accountant.deduct_observations(0, run_input_tokens=2000)

        assert new_run == 2000
        assert token_accountant.usage.input_tokens == 10000

    def test_negative_observations(self, token_accountant: TokenAccountant) -> None:
        """Negative observations - run tokens returned unchanged."""
        token_accountant.usage.input_tokens = 10000

        new_run = token_accountant.deduct_observations(-1, run_input_tokens=2000)

        assert new_run == 2000
        assert token_accountant.usage.input_tokens == 10000

    def test_run_clamps_to_zero(self, token_accountant: TokenAccountant) -> None:
        """Run tokens clamp to 0 when deduction exceeds them."""
        token_accountant.usage.input_tokens = 10000

        new_run = token_accountant.deduct_observations(3, run_input_tokens=100)

        expected = 3 * token_accountant.tokens_per_image
        assert token_accountant.usage.input_tokens == 10000 - expected
        assert new_run == 0

    def test_both_clamp_to_zero(self, token_accountant: TokenAccountant) -> None:
        """Both global and run clamp to 0."""
        token_accountant.usage.input_tokens = 100

        new_run = token_accountant.deduct_observations(3, run_input_tokens=50)

        assert token_accountant.usage.input_tokens == 0
        assert new_run == 0

    def test_usage_already_zero(self, token_accountant: TokenAccountant) -> None:
        """Usage already 0 - deducts nothing from usage, still clamps run."""
        token_accountant.usage.input_tokens = 0

        new_run = token_accountant.deduct_observations(3, run_input_tokens=500)

        assert token_accountant.usage.input_tokens == 0
        assert new_run == 0


@pytest.mark.parametrize(
    ("starting_input_tokens", "input_tokens", "output_tokens", "expected"),
    [
        (5000, 1000, 200, 3800),  # Normal case
        (5000, 0, 0, 5000),  # No tokens to deduct
        (5000, 3000, 1000, 1000),  # Deducting most tokens
        (5000, 3000, 2000, 0),  # Deducting more than available (clamp to 0)
        (500, 300, 100, 100),  # Deducting tokens when close to zero
        (500, 300, 200, 0),  # Deducting tokens that would go negative
    ],
)
def test_deduct_run(
    token_accountant: TokenAccountant,
    starting_input_tokens: int,
    input_tokens: int,
    output_tokens: int,
    expected: int,
) -> None:
    """Test deducting tokens from a removed run."""
    token_accountant.usage.input_tokens = starting_input_tokens

    token_accountant.deduct_run(input_tokens=input_tokens, output_tokens=output_tokens)

    assert token_accountant.usage.input_tokens == expected


class TestEstimateNextRunTokens:
    """Test estimate_next_run_tokens method."""

    def test_estimate_defuser_no_message(
        self, defuser_protocol: PlayerProtocol, capabilities_with_limit: PlayerCapabilities
    ) -> None:
        """Test estimation for defuser without next message."""
        accountant = TokenAccountant(
            capabilities=capabilities_with_limit,
            protocol=defuser_protocol,
            usage=RunUsage(input_tokens=10000, output_tokens=200),
        )

        estimated = accountant.estimate_next_run_tokens()

        assert estimated == accountant.usage.total_tokens + (
            accountant.tokens_per_image * capabilities_with_limit.max_observations_per_request
        )

    def test_estimate_defuser_with_message(
        self, defuser_protocol: PlayerProtocol, capabilities_with_limit: PlayerCapabilities
    ) -> None:
        """Test estimation for defuser with next message."""
        accountant = TokenAccountant(
            capabilities=capabilities_with_limit,
            protocol=defuser_protocol,
            usage=RunUsage(input_tokens=10000, output_tokens=200),
        )

        estimated = accountant.estimate_next_run_tokens(next_message="Hello world")

        assert estimated > accountant.usage.total_tokens + (
            accountant.tokens_per_image * capabilities_with_limit.max_observations_per_request
        )

    def test_estimate_expert_no_images(
        self, expert_protocol: PlayerProtocol, capabilities_with_limit: PlayerCapabilities
    ) -> None:
        """Test estimation for expert (no images)."""
        accountant = TokenAccountant(
            capabilities=capabilities_with_limit,
            protocol=expert_protocol,
            usage=RunUsage(input_tokens=10000, output_tokens=200),
        )

        estimated = accountant.estimate_next_run_tokens()

        assert estimated == accountant.usage.total_tokens

    def test_estimate_with_zero_usage(self, token_accountant: TokenAccountant) -> None:
        """Test estimation with zero usage."""
        estimated = token_accountant.estimate_next_run_tokens()

        assert estimated == token_accountant.tokens_per_image * 3


class TestShouldTruncate:
    """Test should_truncate method."""

    def test_below_threshold(self, token_accountant: TokenAccountant) -> None:
        """Not triggered below threshold."""
        assert token_accountant.usage_limits.input_tokens_limit
        token_accountant.usage.input_tokens = int(
            token_accountant.usage_limits.input_tokens_limit * 0.5
        )
        assert not token_accountant.should_truncate(threshold=0.9)

    def test_above_threshold(self, token_accountant: TokenAccountant) -> None:
        """Triggered above threshold."""
        assert token_accountant.usage_limits.input_tokens_limit
        token_accountant.usage.input_tokens = int(
            token_accountant.usage_limits.input_tokens_limit * 0.95
        )
        assert token_accountant.should_truncate(threshold=0.9)

    def test_no_limit(
        self, defuser_protocol: PlayerProtocol, capabilities_no_limit: PlayerCapabilities
    ) -> None:
        """Never truncates without a limit."""
        accountant = TokenAccountant(
            capabilities=capabilities_no_limit,
            protocol=defuser_protocol,
            usage=RunUsage(input_tokens=999999),
        )
        assert not accountant.should_truncate(threshold=0.9)

    def test_at_exact_threshold(self, token_accountant: TokenAccountant) -> None:
        """Not triggered at exactly the threshold (uses >)."""
        token_accountant.usage.input_tokens = 8745
        assert not token_accountant.should_truncate(threshold=0.9)

    def test_with_next_message(self, token_accountant: TokenAccountant) -> None:
        """A long message pushes over the threshold."""
        token_accountant.usage.input_tokens = 87000
        long_message = "word " * 10000
        assert token_accountant.should_truncate(threshold=0.9, next_message=long_message)
