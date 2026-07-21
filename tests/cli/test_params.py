import pytest

from gptnt.cli import _params


@pytest.fixture(autouse=True)
def _known_configs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the discovered players/providers so the validators test against a fixed set."""
    monkeypatch.setattr(_params, "discover_players", lambda: ["gpt-4o", "claude-sonnet", "dummy"])
    monkeypatch.setattr(_params, "discover_providers", lambda: ["openai", "anthropic"])


def test_player_validator_accepts_a_known_config() -> None:
    _params._validate_player(str, "gpt-4o")  # does not raise


def test_player_validator_rejects_unknown_and_suggests_closest() -> None:
    with pytest.raises(ValueError, match=r"unknown player 'gtp-4o'.*Did you mean 'gpt-4o'"):
        _params._validate_player(str, "gtp-4o")


def test_player_validator_points_at_the_list_command() -> None:
    with pytest.raises(ValueError, match=r"gptnt list players"):
        _params._validate_player(str, "nonsense-xyz")


def test_provider_validator_allows_the_default_none() -> None:
    _params._validate_provider(str, None)  # the unset provider is valid


def test_provider_validator_accepts_a_known_config() -> None:
    _params._validate_provider(str, "openai")  # does not raise


def test_provider_validator_rejects_unknown() -> None:
    with pytest.raises(ValueError, match=r"unknown provider 'openai-typo'"):
        _params._validate_provider(str, "openai-typo")
