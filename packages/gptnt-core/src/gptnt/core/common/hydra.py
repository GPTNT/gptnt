import sys
from pathlib import Path

import hydra
import structlog
from hydra.core.global_hydra import GlobalHydra
from hydra.core.hydra_config import HydraConfig
from omegaconf import DictConfig, OmegaConf

from gptnt.core.common.paths import Paths

logger = structlog.get_logger()

_paths = Paths()


def get_hydra_overrides() -> list[str]:
    """Check and return any Hydra overrides passed as command line arguments."""
    hydra_overrides = sys.argv[1:] if len(sys.argv) > 1 else []
    if hydra_overrides:
        logger.debug(f"Hydra overrides: {hydra_overrides}")
    return hydra_overrides


def _resolve_hydra_config_path() -> str:
    """Resolve the relative config path based on this file's depth within the project."""
    parent_depth = len(Path(__file__).relative_to(Path.cwd()).parts) - 1
    configs_relative_path = str(_paths.configs.relative_to(Path.cwd()))
    return ("../" * parent_depth) + configs_relative_path


def _strip_hydra_metadata(full_cfg: DictConfig) -> DictConfig:
    """Return a copy of the config with Hydra's internal metadata keys removed."""
    app_keys = [str(key) for key in full_cfg if key != "hydra"]
    return OmegaConf.masked_copy(full_cfg, app_keys)


def load_config(*, config_name: str, overrides: list[str] | None = None) -> DictConfig:
    """Load and resolve a Hydra config by name, applying any provided overrides."""
    config_path = _resolve_hydra_config_path()

    GlobalHydra.instance().clear()
    _ = hydra.initialize(config_path=config_path, version_base="1.3")

    full_cfg = hydra.compose(
        config_name=config_name, overrides=overrides or [], return_hydra_config=True
    )
    HydraConfig().cfg = full_cfg
    OmegaConf.resolve(full_cfg)

    return _strip_hydra_metadata(full_cfg)
