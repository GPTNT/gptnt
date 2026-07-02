import sys

import hydra
import structlog
from hydra.core.global_hydra import GlobalHydra
from hydra.core.hydra_config import HydraConfig
from omegaconf import DictConfig, OmegaConf

from gptnt.common.paths import Paths

logger = structlog.get_logger()

_paths = Paths()


def get_hydra_overrides() -> list[str]:
    """Check and return any Hydra overrides passed as command line arguments."""
    hydra_overrides = sys.argv[1:] if len(sys.argv) > 1 else []
    if hydra_overrides:
        logger.debug(f"Hydra overrides: {hydra_overrides}")
    return hydra_overrides


def _strip_hydra_metadata(full_cfg: DictConfig) -> DictConfig:
    """Return a copy of the config with Hydra's internal metadata keys removed."""
    app_keys = [str(key) for key in full_cfg if key != "hydra"]
    return OmegaConf.masked_copy(full_cfg, app_keys)


def compose_player_config(player: str, provider: str | None = None) -> DictConfig:
    """Compose the `player` Hydra config for a player (and optional provider).

    The single shared player-config composition seam: both `gptnt-core`'s model
    validation and `gptnt-statics`'s `ConfigLoader` go through here so they cannot
    diverge. Uses the absolute, context-managed Hydra form (`initialize_config_dir`),
    which works regardless of the current working directory. The returned config is
    composed but **not** resolved or stripped of Hydra metadata; callers instantiate
    subtrees and `OmegaConf.select` directly off it.

    Args:
        player: The player config name to compose (`player=<player>`).
        provider: Optional provider config name (`player/provider=<provider>`).

    Returns:
        The composed (un-resolved) `player` config.
    """
    overrides = [f"player={player}"]
    if provider is not None:
        overrides.append(f"player/provider={provider}")
    # Clear any leftover global Hydra state so the context-managed init below cannot raise "already
    # initialized" if a prior caller left the singleton dirty.
    GlobalHydra.instance().clear()
    with hydra.initialize_config_dir(version_base="1.3", config_dir=str(_paths.configs)):
        return hydra.compose(config_name="player", overrides=overrides)


def load_config(*, config_name: str, overrides: list[str] | None = None) -> DictConfig:
    """Load and resolve a Hydra config by name, applying any provided overrides."""
    # Clear any leftover global Hydra state so the context-managed init cannot raise "already
    # initialized" if a prior caller left the singleton dirty.
    GlobalHydra.instance().clear()
    with hydra.initialize_config_dir(version_base="1.3", config_dir=str(_paths.configs)):
        full_cfg = hydra.compose(
            config_name=config_name, overrides=overrides or [], return_hydra_config=True
        )
        HydraConfig().cfg = full_cfg
        OmegaConf.resolve(full_cfg)
        return _strip_hydra_metadata(full_cfg)
