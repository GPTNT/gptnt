import pytest
from hydra.utils import instantiate
from omegaconf import open_dict

from gptnt.common.hydra import compose_player_config
from gptnt.players.model_settings import fingerprint_model_settings
from gptnt.players.specification import PlayerCapabilities


def test_fingerprint_settings_do_not_remove_nested_ignored_names() -> None:
    selected = fingerprint_model_settings(
        {
            "max_tokens": 1_000,
            "temperature": 0.6,
            "extra_headers": {"Authorization": "secret"},
            "extra_body": {
                "thinking_token_budget": 900,
                "extra_headers": {"model-specific": True},
                "chat_template_kwargs": {"enable_thinking": True},
            },
        }
    )

    assert selected == {
        "max_tokens": 1_000,
        "temperature": 0.6,
        "extra_body": {
            "thinking_token_budget": 900,
            "extra_headers": {"model-specific": True},
            "chat_template_kwargs": {"enable_thinking": True},
        },
    }


@pytest.mark.parametrize(
    ("settings", "expected"),
    [
        pytest.param(None, None, id="absent"),
        pytest.param({}, None, id="empty"),
        pytest.param(
            {"extra_headers": {"Authorization": "secret"}}, None, id="only-ignored-setting"
        ),
    ],
)
def test_empty_fingerprint_settings_are_absent(
    settings: dict[str, object] | None, expected: None
) -> None:
    assert fingerprint_model_settings(settings) is expected


def test_selecting_fingerprint_settings_does_not_mutate_agent_settings() -> None:
    settings = {
        "temperature": 0.6,
        "extra_headers": {"Authorization": "secret"},
        "extra_body": {"chat_template": "template"},
    }

    _ = fingerprint_model_settings(settings)

    assert settings == {
        "temperature": 0.6,
        "extra_headers": {"Authorization": "secret"},
        "extra_body": {"chat_template": "template"},
    }


def test_declared_model_settings_change_the_capability_fingerprint() -> None:
    low_effort = PlayerCapabilities(
        player_name="test-player", player_type="ai", model_settings={"thinking": "low"}
    )
    high_effort = PlayerCapabilities(
        player_name="test-player", player_type="ai", model_settings={"thinking": "high"}
    )

    assert low_effort.fingerprint != high_effort.fingerprint


def test_nested_model_settings_change_the_capability_fingerprint() -> None:
    without_setting = PlayerCapabilities(player_name="test-player", player_type="ai")
    with_setting = PlayerCapabilities(
        player_name="test-player",
        player_type="ai",
        model_settings={"extra_body": {"chat_template": "model-specific-template"}},
    )

    assert without_setting.fingerprint != with_setting.fingerprint


def test_capability_fingerprint_is_independent_of_model_setting_order() -> None:
    first = PlayerCapabilities(
        player_name="test-player",
        player_type="ai",
        model_settings={"temperature": 0.6, "thinking": "low"},
    )
    reordered = PlayerCapabilities(
        player_name="test-player",
        player_type="ai",
        model_settings={"thinking": "low", "temperature": 0.6},
    )

    assert first.fingerprint == reordered.fingerprint


def test_hydra_constructs_capabilities_with_fingerprint_settings() -> None:
    baseline_player = instantiate(compose_player_config("test-defuser").player)
    baseline_capabilities = baseline_player.keywords["capabilities"]

    config = compose_player_config("test-defuser")
    with open_dict(config.player.action_predictor.agent.model_settings):
        config.player.action_predictor.agent.model_settings.extra_headers = {
            "Authorization": "secret"
        }

    player = instantiate(config.player)
    capabilities = player.keywords["capabilities"]
    action_predictor = player.keywords["action_predictor"]
    experiment_recorder = player.keywords["experiment_recorder"]

    assert action_predictor.agent.model_settings["extra_headers"] == {"Authorization": "secret"}
    assert capabilities.model_settings == {"max_tokens": 1_000, "temperature": 0.6}
    assert capabilities.fingerprint == baseline_capabilities.fingerprint
    assert action_predictor.capabilities == capabilities
    assert experiment_recorder.capabilities == capabilities
