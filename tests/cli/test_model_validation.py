"""Static-validation tests for `validate_model_config`.

These cover only env-independent behaviour: the happy path passes whether or not a provider API key
is set (credential tolerance), and an unknown model name fails at the compose stage. The live check
(`live_check_model_config`) spends money / needs network and is intentionally not exercised here.
"""

from gptnt.cli.checks.validation import validate_model_config


def test_unknown_model_fails_at_compose() -> None:
    """An unknown model name fails loudly at the Hydra compose stage."""
    result = validate_model_config("this_model_does_not_exist_xyz")

    assert result.ok is False
    assert result.error_stage == "compose"
    assert result.error
    assert result.capabilities is None
