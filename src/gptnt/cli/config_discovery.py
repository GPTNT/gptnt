from functools import lru_cache

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


@lru_cache
def player_identity(player_name: str) -> PlayerIdentity:  # noqa: WPS231
    """Map a configured `player_name` to its `PlayerIdentity`."""
    for path in paths.player_configs.glob("*.yaml"):
        config = yaml.safe_load(path.read_text()) or {}
        if (config.get("capabilities") or {}).get("player_name") != player_name:
            continue

        try:
            return PlayerIdentity.model_validate(config.get("identity"))
        except ValidationError as error:
            raise ValueError(f"Invalid `identity` block in {path}") from error

    raise ValueError(f"Identity for player not found: {player_name}")
