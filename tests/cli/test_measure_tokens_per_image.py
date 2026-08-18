import pytest
from pydantic_ai import BinaryContent, ModelSettings, RunUsage

from gptnt.cli.checks.players import PlayerDetail, PlayerReport, check_tokens_per_image
from gptnt.cli.checks.validation import ModelValidationResult
from gptnt.cli.onboarding.measure_tokens_per_image import _insert_tokens_per_image, _measure
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


class _CalibrationAgent:
    def __init__(self, *, max_tokens: int) -> None:
        self.model_settings: ModelSettings = {"max_tokens": max_tokens, "temperature": 0.2}
        self.seen_settings: list[ModelSettings] = []

    async def run(
        self, prompt: list[str | BinaryContent], *, model_settings: ModelSettings
    ) -> object:
        self.seen_settings.append(model_settings)
        input_tokens = 150 if any(isinstance(part, BinaryContent) for part in prompt) else 100
        return type("Result", (), {"usage": RunUsage(input_tokens=input_tokens)})()


@pytest.mark.anyio
@pytest.mark.parametrize(("configured", "expected"), [(16, 256), (1_000, 1_000)])
async def test_measure_preserves_settings_and_allows_reasoning_output(
    configured: int, expected: int
) -> None:
    agent = _CalibrationAgent(max_tokens=configured)

    baseline, with_image = await _measure(agent, b"image")

    assert (baseline, with_image) == (100, 150)
    assert len(agent.seen_settings) == 2
    assert all(settings.get("max_tokens") == expected for settings in agent.seen_settings)
    assert all(
        settings.get("temperature") == pytest.approx(0.2) for settings in agent.seen_settings
    )
