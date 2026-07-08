"""`player_identity` resolves one model's leaderboard identity lazily, from its own config.

The point of the lazy, per-name lookup: a malformed `identity` block in an *unrelated* model's
config must never be validated (so it can't block a good submission), and a malformed block on the
*requested* model must fail loudly, naming the offending file.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest
import yaml

from gptnt.cli import config_discovery

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

_VALID_IDENTITY: dict[str, Any] = {
    "display_name": "Good Model",
    "organisation": "GPTNT",
    "is_os_model": False,
    "url": "https://example.com/good",
}


def _write_config(
    configs_dir: Path, stem: str, *, player_name: str, identity: dict[str, Any] | None
) -> None:
    payload: dict[str, Any] = {"capabilities": {"player_name": player_name}}
    if identity is not None:
        payload["identity"] = identity
    _ = (configs_dir / f"{stem}.yaml").write_text(yaml.safe_dump(payload))


@pytest.fixture
def configs_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point `player_identity` at a temp configs dir and clear its cache around the test."""
    monkeypatch.setattr(config_discovery, "paths", SimpleNamespace(player_configs=tmp_path))
    config_discovery.player_identity.cache_clear()
    yield tmp_path
    config_discovery.player_identity.cache_clear()


def test_resolves_a_configured_identity(configs_dir: Path) -> None:
    _write_config(configs_dir, "good", player_name="good-model", identity=_VALID_IDENTITY)
    assert config_discovery.player_identity("good-model").organisation == "GPTNT"


def test_raises_when_no_config_matches(configs_dir: Path) -> None:
    _write_config(configs_dir, "good", player_name="good-model", identity=_VALID_IDENTITY)
    # A submission must be attributable, so an unknown player is a hard error, not a blank.
    with pytest.raises(ValueError, match="absent-model"):
        _ = config_discovery.player_identity("absent-model")


def test_a_malformed_unrelated_config_does_not_block_a_good_lookup(configs_dir: Path) -> None:
    _write_config(configs_dir, "good", player_name="good-model", identity=_VALID_IDENTITY)
    # Missing display_name/is_os_model/url — invalid, but for a model we are not resolving.
    _write_config(configs_dir, "bad", player_name="bad-model", identity={"organisation": "X"})
    assert config_discovery.player_identity("good-model").organisation == "GPTNT"


def test_a_malformed_identity_on_the_requested_model_names_the_file(configs_dir: Path) -> None:
    _write_config(configs_dir, "bad", player_name="bad-model", identity={"organisation": "X"})
    with pytest.raises(ValueError, match=r"bad\.yaml"):
        _ = config_discovery.player_identity("bad-model")
