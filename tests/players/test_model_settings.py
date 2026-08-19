import pytest
from hydra.utils import instantiate
from omegaconf import open_dict
from pydantic import BaseModel, SecretBytes, SecretStr, ValidationError
from pydantic_ai import ModelSettings
from pydantic_ai.models.anthropic import AnthropicModelSettings
from pydantic_ai.models.google import GoogleModelSettings
from pydantic_ai.models.openai import OpenAIChatModelSettings

from gptnt.common.hydra import compose_player_config
from gptnt.players.model_settings import _IGNORED_MODEL_SETTINGS, fingerprint_model_settings


class _UnsupportedSettingsModel(BaseModel):
    setting: str


_PYDANTIC_AI_SETTINGS_FIELDS = (
    ModelSettings.__annotations__,
    OpenAIChatModelSettings.__annotations__,
    AnthropicModelSettings.__annotations__,
    GoogleModelSettings.__annotations__,
)
_PYDANTIC_AI_SETTINGS_CASES = (
    pytest.param(_PYDANTIC_AI_SETTINGS_FIELDS[0], id="common"),
    pytest.param(_PYDANTIC_AI_SETTINGS_FIELDS[1], id="openai-chat"),
    pytest.param(_PYDANTIC_AI_SETTINGS_FIELDS[2], id="anthropic"),
    pytest.param(_PYDANTIC_AI_SETTINGS_FIELDS[3], id="google"),
)
_EXPECTED_IGNORED_MODEL_SETTINGS = frozenset(
    (
        "anthropic_cache",
        "anthropic_cache_instructions",
        "anthropic_cache_messages",
        "anthropic_cache_tool_definitions",
        "anthropic_eager_input_streaming",
        "anthropic_metadata",
        "anthropic_service_tier",
        "anthropic_speed",
        "extra_headers",
        "google_cloud_service_tier",
        "google_labels",
        "google_logprobs",
        "google_top_logprobs",
        "openai_continuous_usage_stats",
        "openai_logprobs",
        "openai_prompt_cache_key",
        "openai_prompt_cache_retention",
        "openai_service_tier",
        "openai_store",
        "openai_top_logprobs",
        "openai_user",
        "service_tier",
        "timeout",
    )
)
_EXPECTED_CAPTURED_MODEL_SETTINGS = frozenset(
    (
        "anthropic_betas",
        "anthropic_code_execution_tool_version",
        "anthropic_container",
        "anthropic_context_management",
        "anthropic_effort",
        "anthropic_task_budget",
        "anthropic_thinking",
        "extra_body",
        "frequency_penalty",
        "google_cached_content",
        "google_safety_settings",
        "google_thinking_config",
        "google_video_resolution",
        "logit_bias",
        "max_tokens",
        "openai_reasoning_effort",
        "openai_prediction",
        "parallel_tool_calls",
        "presence_penalty",
        "seed",
        "stop_sequences",
        "temperature",
        "thinking",
        "tool_choice",
        "top_k",
        "top_p",
    )
)


def test_pydantic_ai_model_settings_have_an_explicit_fingerprint_policy() -> None:
    declared_settings = frozenset().union(
        *(settings_fields.keys() for settings_fields in _PYDANTIC_AI_SETTINGS_FIELDS)
    )

    assert _IGNORED_MODEL_SETTINGS == _EXPECTED_IGNORED_MODEL_SETTINGS
    assert declared_settings == (
        _EXPECTED_CAPTURED_MODEL_SETTINGS | _EXPECTED_IGNORED_MODEL_SETTINGS
    )


def test_common_pydantic_ai_settings_follow_fingerprint_policy() -> None:
    settings = ModelSettings(
        max_tokens=1_000,
        temperature=0.6,
        top_p=0.9,
        top_k=40,
        timeout=30,
        parallel_tool_calls=False,
        tool_choice="auto",
        seed=42,
        presence_penalty=0.1,
        frequency_penalty=0.2,
        logit_bias={"123": -10},
        stop_sequences=["STOP"],
        extra_headers={"Authorization": "secret"},
        thinking="high",
        service_tier="priority",
        extra_body={"model_specific_option": True},
    )

    selected = fingerprint_model_settings(settings)

    assert selected == {
        key: setting_value
        for key, setting_value in settings.items()
        if key not in _IGNORED_MODEL_SETTINGS
    }


@pytest.mark.parametrize("declared_fields", _PYDANTIC_AI_SETTINGS_CASES)
def test_every_declared_pydantic_ai_setting_follows_fingerprint_policy(
    declared_fields: dict[str, object],
) -> None:
    settings = {
        setting_name: {"declared_setting": setting_name} for setting_name in declared_fields
    }

    selected = fingerprint_model_settings(settings)

    assert selected == {
        setting_name: setting_value
        for setting_name, setting_value in settings.items()
        if setting_name not in _IGNORED_MODEL_SETTINGS
    }


@pytest.mark.parametrize("ignored_setting", sorted(_EXPECTED_IGNORED_MODEL_SETTINGS))
def test_each_ignored_model_setting_is_removed(ignored_setting: str) -> None:
    selected = fingerprint_model_settings(
        {"thinking": "low", ignored_setting: {"ignored": ignored_setting}}
    )

    assert selected == {"thinking": "low"}


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
    "unsupported_setting",
    [
        pytest.param(dict, id="callable"),
        pytest.param(b"binary", id="bytes"),
        pytest.param(SecretStr("secret"), id="secret-string"),
        pytest.param(SecretBytes(b"secret"), id="secret-bytes"),
        pytest.param(_UnsupportedSettingsModel(setting="value"), id="pydantic-model"),
    ],
)
def test_non_json_model_settings_are_rejected(unsupported_setting: object) -> None:
    with pytest.raises(ValidationError, match="valid JSON value"):
        _ = fingerprint_model_settings({"unsupported": unsupported_setting})


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


def test_all_json_value_shapes_are_preserved() -> None:
    settings = {
        "none": None,
        "boolean": True,
        "integer": 1,
        "float": 0.5,
        "string": "value",
        "array": [None, False, 2, 0.25, "entry", {"nested": "mapping"}],
        "mapping": {"nested": [1, 2, 3]},
    }

    assert fingerprint_model_settings(settings) == settings


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


@pytest.mark.parametrize("ignored_setting", sorted(_EXPECTED_IGNORED_MODEL_SETTINGS))
def test_ignored_settings_do_not_change_selected_model_settings(ignored_setting: str) -> None:
    without_ignored_setting = fingerprint_model_settings({"thinking": "low"})
    with_ignored_setting = fingerprint_model_settings(
        {"thinking": "low", ignored_setting: {"ignored": ignored_setting}}
    )

    assert without_ignored_setting == with_ignored_setting


def test_hydra_constructs_capabilities_with_fingerprint_settings() -> None:
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
    assert capabilities.model.settings == {"max_tokens": 1_000, "temperature": 0.6}
    assert action_predictor.capabilities == capabilities
    assert experiment_recorder.capabilities == capabilities
