import pytest

from gptnt.cli.checks.players import PlayerDetail, PlayerReport, check_tokens_per_image
from gptnt.cli.checks.validation import ModelValidationResult
from gptnt.cli.onboarding.measure_tokens_per_image import _insert_tokens_per_image
from gptnt.players.specification import PlayerCapabilities

_CONFIG_WITH_COMMENT = """# @package player

capabilities:
  player_name: claude-sonnet-4-6
  # keep this comment
  usage_limits:
    input_tokens_limit: 200000

action_predictor:
  agent:
    model:
      model_name: claude-sonnet-4-6
"""


def test_insert_adds_line_under_capabilities_preserving_comments() -> None:
    result = _insert_tokens_per_image(_CONFIG_WITH_COMMENT, 424)
    assert "  tokens_per_image: 424\n" in result
    # inserted just below player_name, matching the checked-in config key order
    assert result.index("player_name") < result.index("tokens_per_image: 424")
    assert result.index("tokens_per_image: 424") < result.index("# keep this comment")
    # every other line survives byte-for-byte
    assert "# keep this comment" in result
    assert "input_tokens_limit: 200000" in result
    assert result.index("tokens_per_image") < result.index("action_predictor")


def test_insert_replaces_existing_value() -> None:
    seeded = _insert_tokens_per_image(_CONFIG_WITH_COMMENT, 111)
    updated = _insert_tokens_per_image(seeded, 222)
    assert "tokens_per_image: 222" in updated
    assert "tokens_per_image: 111" not in updated
    assert updated.count("tokens_per_image:") == 1


def test_insert_without_capabilities_block_raises() -> None:
    with pytest.raises(RuntimeError, match="capabilities"):
        _ = _insert_tokens_per_image("# @package player\n\nidentity:\n  display_name: X\n", 424)


def _detail(label: str, tokens_per_image: int) -> PlayerDetail:
    capabilities = PlayerCapabilities(
        player_name=label, player_type="ai", tokens_per_image=tokens_per_image
    )
    return PlayerDetail(
        report=PlayerReport(label, "pass", "pass", "skip", ""),
        static=ModelValidationResult(label, None, ok=True, capabilities=capabilities),
    )


def test_tokens_per_image_fails_uncalibrated_player() -> None:
    finding = check_tokens_per_image([_detail("claude-sonnet-4-6", 0)])[0]
    assert finding.status == "fail"
    assert "measure-tokens-per-image claude-sonnet-4-6" in finding.hint


def test_tokens_per_image_passes_calibrated_player() -> None:
    finding = check_tokens_per_image([_detail("gpt-5", 383)])[0]
    assert finding.status == "pass"
    assert "383" in finding.detail


def test_tokens_per_image_skips_uninstantiated_config() -> None:
    detail = PlayerDetail(
        report=PlayerReport("broken", "pass", "fail", "skip", "boom"),
        static=ModelValidationResult("broken", None, ok=False, capabilities=None),
    )
    assert check_tokens_per_image([detail]) == []
