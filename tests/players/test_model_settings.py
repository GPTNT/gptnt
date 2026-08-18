from enum import Enum

import pytest

from gptnt.players.model_settings import capabilities_with_model_settings, normalize_model_settings
from gptnt.players.specification import PlayerCapabilities


class _Mode(Enum):
    deterministic = "deterministic"


def test_normalization_preserves_inference_settings_and_removes_unsafe_state() -> None:
    normalized = normalize_model_settings(
        {
            "_target_": "some.SettingsClass",
            "max_tokens": 1_000,
            "temperature": 0.6,
            "mode": _Mode.deterministic,
            "extra_headers": {"Authorization": "secret"},
            "extra_body": {
                "thinking_token_budget": 900,
                "api-key": "secret",
                "chat_template_kwargs": {"enable_thinking": True, "reasoning_budget": 850},
            },
        }
    )

    assert normalized == {
        "max_tokens": 1_000,
        "temperature": 0.6,
        "mode": "deterministic",
        "extra_body": {
            "thinking_token_budget": 900,
            "chat_template_kwargs": {"enable_thinking": True, "reasoning_budget": 850},
        },
    }


@pytest.mark.parametrize("settings", [dict, {"callback": dict}])
def test_callable_model_settings_are_rejected(settings: object) -> None:
    with pytest.raises(TypeError, match=r"(?i)callable"):
        _ = normalize_model_settings(settings)


def test_effective_model_settings_change_the_capability_fingerprint() -> None:
    capabilities = PlayerCapabilities(player_name="test-player", player_type="ai")

    with_low_effort = capabilities_with_model_settings(capabilities, {"thinking": "low"})
    with_high_effort = capabilities_with_model_settings(capabilities, {"thinking": "high"})

    assert with_low_effort.model_settings == {"thinking": "low"}
    assert with_low_effort.fingerprint != with_high_effort.fingerprint
    assert capabilities.model_settings is None
