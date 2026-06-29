from functools import lru_cache

from gptnt.common.paths import Paths

paths = Paths()


@lru_cache
def discover_models() -> list[str]:
    """Return sorted list of available model names from configs/model/*.yaml."""
    if not paths.model_configs.is_dir():
        return []
    return sorted(path.stem for path in paths.model_configs.glob("*.yaml"))


@lru_cache
def discover_suites() -> list[str]:
    """Return sorted list of available suite ids from configs/suites/*.yaml."""
    if not paths.suite_configs.is_dir():
        return []
    return sorted(path.stem for path in paths.suite_configs.glob("*.yaml"))


@lru_cache
def discover_providers() -> list[str]:
    """Return sorted list of available provider names from configs/model/provider/*.yaml."""
    provider_config_dir = paths.model_configs / "provider"
    if not provider_config_dir.is_dir():
        return []
    return sorted(path.stem for path in provider_config_dir.glob("*.yaml"))
