from functools import lru_cache

import yaml

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
def player_identities() -> dict[str, PlayerIdentity]:
    """Map each configured `player_name` to its `PlayerIdentity` (leaderboard attribution).

    Read straight from `configs/player/*.yaml`.
    """
    identities: dict[str, PlayerIdentity] = {}

    for path in paths.player_configs.glob("*.yaml"):
        config = yaml.safe_load(path.read_text()) or {}
        player_name = (config.get("capabilities") or {}).get("player_name")
        identity = config.get("identity")
        if player_name and identity:
            identities[player_name] = PlayerIdentity.model_validate(identity)

    return identities
