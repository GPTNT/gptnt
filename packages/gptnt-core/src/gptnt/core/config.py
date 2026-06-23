from functools import lru_cache

from pydantic import BaseModel, ConfigDict, Field

from gptnt.core.common.paths import Paths

paths = Paths()

MODEL_CONFIG_DIR = paths.configs / "model"
EXPERIMENT_CONFIG_DIR = paths.configs / "experiment"


@lru_cache
def discover_models() -> list[str]:
    """Return sorted list of available model names from configs/model/*.yaml."""
    if not MODEL_CONFIG_DIR.is_dir():
        return []
    return sorted(path.stem for path in MODEL_CONFIG_DIR.glob("*.yaml"))


@lru_cache
def discover_experiments() -> list[str]:
    """Return sorted list of available experiment preset names from configs/experiment/*.yaml."""
    if not EXPERIMENT_CONFIG_DIR.is_dir():
        return []
    return sorted(path.stem for path in EXPERIMENT_CONFIG_DIR.glob("*.yaml"))


@lru_cache
def discover_providers() -> list[str]:
    """Return sorted list of available provider names from configs/model/provider/*.yaml."""
    provider_config_dir = MODEL_CONFIG_DIR / "provider"
    if not provider_config_dir.is_dir():
        return []
    return sorted(path.stem for path in provider_config_dir.glob("*.yaml"))


class PlayerSpec(BaseModel):
    """One player in a roster: a model config, an optional provider override, and a count."""

    model_config = ConfigDict(extra="forbid")

    model: str
    """A `configs/model/<model>.yaml` config name."""

    provider: str | None = None
    """A `configs/model/provider/<provider>.yaml` config name, or `None` to use the default."""

    count: int = Field(default=1, ge=1)
    """How many copies of this player to spawn."""
