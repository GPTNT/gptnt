from pathlib import Path

from omegaconf import OmegaConf
from pytest_cases import fixture, param_fixture

from gptnt.players.metrics.cost import load_model_token_cost

CONFIG_DIR = Path.cwd().joinpath("configs")
MODELS_DIR = CONFIG_DIR.joinpath("model")

model_config_name = param_fixture(
    "model_config_name",
    ["gpt4o", "gpt41", "claude37", "claude37_bedrock", "gemini-2", "gemini-25"],
    scope="session",
)


@fixture(scope="session")
def model_name(model_config_name: Path) -> str:
    """Fixture to get the model name from the model path."""
    model_path = MODELS_DIR.joinpath(f"{model_config_name}.yaml")
    model_content = OmegaConf.load(model_path)
    model_name = model_content["agent"]["model"]["model_name"]
    assert isinstance(model_name, str)
    return model_name


def test_cost_exists_for_all_models(model_name: str) -> None:
    token_cost = load_model_token_cost(model_name=model_name)
    assert token_cost.input_token_cost > 0
    assert token_cost.output_token_cost > 0
