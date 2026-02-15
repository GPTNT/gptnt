from pathlib import Path

import hydra
import pytest
from hydra.core.hydra_config import HydraConfig
from omegaconf import DictConfig, open_dict, read_write
from pytest_cases import param_fixture

CONFIG_DIR = Path.cwd().joinpath("configs")
PLAYER_CONFIG = CONFIG_DIR.joinpath("player.yaml")
MODEL_DIR = CONFIG_DIR.joinpath("model")

model = param_fixture(
    "model", [path.stem for path in MODEL_DIR.glob("[!_]*.yaml")], scope="session"
)


def load_hydra_config(
    config_dir: Path, config_file_name: str, overrides: list[str] | None = None
) -> DictConfig:
    overrides = overrides or []

    with hydra.initialize_config_dir(config_dir=str(config_dir.resolve()), version_base="1.3"):
        config = hydra.compose(
            config_name=config_file_name, return_hydra_config=True, overrides=overrides
        )
        HydraConfig.instance().set_config(config)

    # Remove the hydra key from the config
    with read_write(config), open_dict(config):
        config["hydra"] = None

    return config


def test_ai_player_config_is_valid(model: str) -> None:
    """Test that the players can be instantiated from Hydra."""
    config = load_hydra_config(
        config_dir=PLAYER_CONFIG.parent,
        config_file_name=PLAYER_CONFIG.name,
        overrides=[f"model={model}"],
    )

    assert config


@pytest.mark.skip(reason="This does not work on CI because there are no API keys to try with.")
def test_ai_player_can_instantiate_from_config(model: str) -> None:
    """Test that the players can be instantiated using Hydra.

    Note that this only uses the TestModel and not the actual models.
    """
    config = load_hydra_config(
        config_dir=PLAYER_CONFIG.parent,
        config_file_name=PLAYER_CONFIG.name,
        overrides=[f"model={model}"],
    )

    # Check that the player can be instantiated
    instantiated_player = hydra.utils.instantiate(config.player)
    assert instantiated_player
