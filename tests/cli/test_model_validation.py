"""Static validation and shared player-configuration resolution."""

from types import SimpleNamespace

import pytest
from omegaconf import open_dict

from gptnt.cli.checks import validation
from gptnt.cli.statics._config_loader import ConfigLoader
from gptnt.common.hydra import compose_player_config
from gptnt.interactive.entrypoints.run_player import (
    _instantiate_player_partial,
    load_player_config,
)
from gptnt.players.configuration import resolve_player_config


def test_unknown_model_fails_at_compose() -> None:
    """An unknown model name fails loudly at the Hydra compose stage."""
    result = validation.validate_model_config("this_model_does_not_exist_xyz")

    assert result.ok is False
    assert result.error_stage == "compose"
    assert result.error
    assert result.capabilities is None


def test_string_model_validation_accepts_the_qualified_runtime_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = compose_player_config("test-defuser")
    with open_dict(config.player.capabilities.model):
        config.player.capabilities.model.name = "gpt-5.2"
        config.player.capabilities.model.provider = "openai"

    monkeypatch.setattr(validation, "compose_player_config", lambda *_: config)
    monkeypatch.setattr(
        validation, "instantiate", lambda _: SimpleNamespace(model="openai:gpt-5.2")
    )

    result = validation.validate_model_config("test-defuser")

    assert result.ok is True
    assert result.resolved_model_name == "openai:gpt-5.2"


def test_presentation_and_credentials_are_outside_capability_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    credential_material = "not-for-recording"
    monkeypatch.setenv("VLLM_API_KEY", credential_material)
    original = resolve_player_config(compose_player_config("qwen3-5-27b", "vllm_box1"))
    renamed = resolve_player_config(
        compose_player_config(
            "qwen3-5-27b", "vllm_box1", overrides=["player.identity.display_name=Renamed"]
        )
    )

    serialized_identity = original.capabilities.model_dump_json()
    assert original.identity != renamed.identity
    assert original.capabilities.fingerprint == renamed.capabilities.fingerprint
    assert credential_material not in serialized_identity


def test_interactive_and_statics_resolve_the_same_player_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "not-used")
    interactive = load_player_config(["player=gpt-5-2"])
    statics = ConfigLoader(player="gpt-5-2", provider=None, role="defuser").resolved
    player_partial = _instantiate_player_partial(interactive)

    assert interactive.capabilities.model_dump_json() == statics.capabilities.model_dump_json()
    assert interactive.capabilities.fingerprint == statics.capabilities.fingerprint
    assert player_partial.keywords["capabilities"] is interactive.capabilities
    assert player_partial.keywords["action_predictor"].agent.model.model_name == "gpt-5.2"
