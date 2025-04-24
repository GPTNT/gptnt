from pathlib import Path

import hydra
from hydra.core.hydra_config import HydraConfig
from omegaconf import DictConfig, open_dict, read_write
from pytest_cases import param_fixture

CONFIG_DIR = Path.cwd().joinpath("configs")
PLAYER_CONFIG = CONFIG_DIR.joinpath("player.yaml")
AI_PLAYER_DIR = CONFIG_DIR.joinpath("player/ai")
SYSTEM_PROMPT_DIR = CONFIG_DIR.joinpath("system_prompt")

ai_player = param_fixture(
    "ai_player", [path.stem for path in AI_PLAYER_DIR.glob("[!_]*.yaml")], scope="session"
)

system_prompt = param_fixture(
    "system_prompt",
    [
        path.stem
        for path in SYSTEM_PROMPT_DIR.glob("[!_]*.yaml")
        # Exclude the file named "none" since AI must have a system prompt
        if path.stem != "none"
    ],
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


def test_ai_player_config_is_valid(ai_player: str, system_prompt: str) -> None:
    """Test that the players can be instantiated from Hydra."""
    config = load_hydra_config(
        config_dir=PLAYER_CONFIG.parent,
        config_file_name=PLAYER_CONFIG.name,
        overrides=[f"player=ai/{ai_player}", f"system_prompt={system_prompt}", "model=test"],
    )

    assert config


def test_ai_player_can_instantiate_from_config(ai_player: str, system_prompt: str) -> None:
    """Test that the players can be instantiated using Hydra.

    Note that this only uses the TestModel and not the actual models.
    """
    config = load_hydra_config(
        config_dir=PLAYER_CONFIG.parent,
        config_file_name=PLAYER_CONFIG.name,
        overrides=[f"player=ai/{ai_player}", f"system_prompt={system_prompt}", "model=test"],
    )

    # Check that the player can be instantiated
    instantiated_player = hydra.utils.instantiate(config.player)
    assert instantiated_player
