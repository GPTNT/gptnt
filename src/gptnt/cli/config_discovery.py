from functools import lru_cache

from gptnt.common.paths import Paths

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
