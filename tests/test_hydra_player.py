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
providers = param_fixture(
    "provider",
    [None, *[path.stem for path in MODEL_DIR.glob("provider/[!_]*.yaml")]],
    scope="session",
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


def test_ai_player_config_is_valid(model: str, provider: str | None) -> None:
    """Test that the players can be instantiated from Hydra."""
    overrides = [f"model={model}"]
    if provider:
        overrides.append(f"model/provider={provider}")

    config = load_hydra_config(
        config_dir=PLAYER_CONFIG.parent, config_file_name=PLAYER_CONFIG.name, overrides=overrides
    )

    assert config


@pytest.mark.skip(reason="This doesn't work on CI because we don't have the API keys there.")
def test_ai_player_can_instantiate_from_config(model: str, provider: str | None) -> None:
    """Test that the players can be instantiated using Hydra."""
    if model.startswith("test") and provider is not None:
        pytest.skip("Test models should not have a provider specified.")

    overrides = [f"model={model}", "+player.action_predictor.agent.defer_model_check=True"]
    if provider:
        overrides.append(f"model/provider={provider}")

    config = load_hydra_config(
        config_dir=PLAYER_CONFIG.parent, config_file_name=PLAYER_CONFIG.name, overrides=overrides
    )

    # Check that the player can be instantiated
    instantiated_player = hydra.utils.instantiate(config.player)
    assert instantiated_player
