from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from gptnt.common.paths import Paths
from gptnt.players.specification import PlayerIdentity

paths = Paths()


@lru_cache
def discover_players() -> list[str]:
    """Return sorted list of available player names from configs/player/*.yaml."""
    if not paths.player_configs.is_dir():
        return []
    return sorted(path.stem for path in paths.player_configs.glob("*.yaml"))


@lru_cache
def discover_suites() -> list[str]:
    """Return sorted list of available suite ids from configs/suites/*.yaml."""
    if not paths.suite_configs.is_dir():
        return []
    return sorted(path.stem for path in paths.suite_configs.glob("*.yaml"))


@lru_cache
def discover_providers() -> list[str]:
    """Return sorted list of available provider names from configs/player/provider/*.yaml."""
    provider_config_dir = paths.player_configs / "provider"
    if not provider_config_dir.is_dir():
        return []
    return sorted(path.stem for path in provider_config_dir.glob("*.yaml"))


def _config_for_player(player_name: str) -> tuple[Path, dict[str, Any]] | None:
    """The `(path, parsed config)` whose capabilities name matches `player_name`, or `None`."""
    for path in paths.player_configs.glob("*.yaml"):
        config = yaml.safe_load(path.read_text()) or {}
        if (config.get("capabilities") or {}).get("player_name") == player_name:
            return path, config
    return None


@lru_cache
def player_identity(player_name: str) -> PlayerIdentity:
    """Resolve a configured `player_name` to its `PlayerIdentity`, naming the file on a bad block.

    Only the requested model's `identity` block is validated, so a malformed block in an unrelated
    config cannot block a good submission. A bad block on the requested model raises with the file
    named, which the bare pydantic error cannot say.
    """
    match = _config_for_player(player_name)
    if match is None:
        raise ValueError(f"Identity for player not found: {player_name}")
    path, config = match
    try:
        return PlayerIdentity.model_validate(config.get("identity"))
    except ValidationError as error:
        raise ValueError(f"Invalid `identity` block in {path}") from error
