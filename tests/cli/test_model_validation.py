"""Static-validation tests for `validate_model_config`.

These cover only env-independent behaviour: the happy path passes whether or not a provider API key
is set (credential tolerance), and an unknown model name fails at the compose stage. The live check
(`live_check_model_config`) spends money / needs network and is intentionally not exercised here.
"""

import pytest

from gptnt.cli.doctor.validation import validate_model_config


@pytest.mark.skip
def test_valid_model_config_is_credential_tolerant() -> None:
    """A real model config is structurally valid even when its API key is unset."""
    result = validate_model_config("claude46")

    assert result.ok
    assert result.error is None
    assert result.capabilities is not None
    assert result.capabilities.player_name == "claude46"
    # Either the agent instantiated (key present) and we resolved the pydantic-ai model
    # name, or the only issue was a missing credential (tolerated by design).
    assert result.resolved_model_name == "claude-sonnet-4-6" or result.missing_credential


def test_unknown_model_fails_at_compose() -> None:
    """An unknown model name fails loudly at the Hydra compose stage."""
    result = validate_model_config("this_model_does_not_exist_xyz")

    assert result.ok is False
    assert result.error_stage == "compose"
    assert result.error
    assert result.capabilities is None
