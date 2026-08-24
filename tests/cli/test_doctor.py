"""Tests for `gptnt doctor`.

Coverage is the deterministic, infra-free surface: the model-result mapping, the display-gating
logic, the small text/path helpers, the summary tally, and the two async paths that need neither
network nor a spawned game (a dummy model check, and the mod-load gate that must *skip* — not spawn
— when a prerequisite already failed). The infra checks themselves (Redis/EM/otel/game spawn) are
environment-dependent and verified by running `gptnt doctor` directly.
"""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock

import pytest

from gptnt.cli import integrity
from gptnt.cli.__main__ import build_app
from gptnt.cli.checks import game, machine, players, render, services
from gptnt.cli.checks.result import CheckResult
from gptnt.cli.checks.validation import ModelValidationResult
from gptnt.cli.doctor import command
from gptnt.provenance import BenchmarkIntegrityError

from tests._cli_runner import invoke_cli


def _unavailable_benchmark(_repository: object) -> object:
    raise BenchmarkIntegrityError("no release reference")


async def _unexpected_infrastructure_check(*_args: object, **_kwargs: object) -> object:
    raise AssertionError("--config-only must not run infrastructure checks")


def _unexpected_machine_check() -> object:
    raise AssertionError("--config-only must not run machine checks")


def test_static_boxes_ok_is_exists_and_instantiates() -> None:
    outcome = ModelValidationResult("m", None, ok=True, resolved_model_name="vendor:thing")
    exists, instantiates, note = players._static_boxes(outcome)
    assert (exists, instantiates) == ("pass", "pass")
    assert "vendor:thing" in note


def test_static_boxes_compose_fail_is_exists_fail() -> None:
    outcome = ModelValidationResult("m", None, ok=False, error_stage="compose", error="bad yaml")
    exists, instantiates, _ = players._static_boxes(outcome)
    # A config that doesn't compose doesn't "exist"; instantiation can't even be attempted.
    assert (exists, instantiates) == ("fail", "skip")


def test_static_boxes_agent_fail_is_instantiate_fail() -> None:
    outcome = ModelValidationResult("m", None, ok=False, error_stage="agent", error="boom")
    exists, instantiates, _ = players._static_boxes(outcome)
    assert (exists, instantiates) == ("pass", "fail")


def test_static_boxes_missing_credential_is_instantiate_fail() -> None:
    outcome = ModelValidationResult(
        "m",
        None,
        ok=True,
        missing_credential=True,
        error="Set the FOO_API_KEY environment variable",
    )
    exists, instantiates, note = players._static_boxes(outcome)
    # An unset provider key composes but can't run, so the doctor fails it (not a warn).
    assert (exists, instantiates) == ("pass", "fail")
    # The note surfaces pydantic-ai's own message (which names the var) — no maintained map.
    assert "FOO_API_KEY" in note


def test_model_report_failed_only_on_fail_box() -> None:
    assert players.PlayerReport("m", "pass", "fail", "skip").failed is True
    assert players.PlayerReport("m", "pass", "warn", "skip").failed is False
    assert players.PlayerReport("m", "pass", "pass", "skip").failed is False


def test_doctor_config_only_renders_clean_benchmark_and_checks_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(command, "discover_players", lambda: ["test-random"])
    monkeypatch.setattr(command, "_infrastructure_checks", _unexpected_infrastructure_check)
    monkeypatch.setattr(command, "check_machine", _unexpected_machine_check)

    result = invoke_cli(build_app(), ["doctor", "--config-only"])

    assert result.exit_code == 0, result.output
    assert "Benchmark" in result.output
    assert "Reference" in result.output
    assert "v2.0.0" in result.output
    assert "Release commit" in result.output
    assert "abc1234" in result.output
    assert "Protected content" in result.output
    assert "matches" in result.output
    assert "test-random" in result.output
    assert "Infrastructure" not in result.output


def test_doctor_force_runs_infrastructure_without_release_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    infrastructure = AsyncMock(return_value=[CheckResult.passed("Mod load", "loaded")])

    monkeypatch.setattr(integrity, "check_benchmark_integrity", _unavailable_benchmark)
    monkeypatch.setattr(command, "_infrastructure_checks", infrastructure)
    monkeypatch.setattr(command, "check_machine", list)

    result = invoke_cli(
        build_app(), ["doctor", "runs/quickstart.yaml", "--check-mod-load", "--force"]
    )

    assert result.exit_code == 0, result.output
    infrastructure.assert_awaited_once_with(check_mod_load=True)
    assert "no release reference" in result.output
    assert "Mod load" in result.output


def test_display_skipped_off_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    result = game.check_display()
    assert result.status == "skip"


def test_display_fails_on_linux_without_display(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("DISPLAY", raising=False)
    result = game.check_display()
    assert result.status == "fail"
    assert "startx" in result.hint


def test_short_collapses_and_caps() -> None:
    assert render._short("a\n  b\t c") == "a b c"
    assert render._short(None) == ""
    capped = render._short("word " * 200)
    assert len(capped) <= render._MESSAGE_CAP
    assert capped.endswith("…")


def test_nearest_existing_walks_up_to_a_real_ancestor(tmp_path) -> None:
    missing = tmp_path / "a" / "b" / "c"
    assert machine._nearest_existing(missing) == tmp_path


@pytest.mark.anyio
async def test_redis_ping_false_when_nothing_listens() -> None:
    """A closed port is not a reachable Redis (guards against reporting bare-port-open as ✓)."""
    assert await services._redis_pings("127.0.0.1", 59999) is False


@pytest.mark.anyio
async def test_http_probe_false_when_nothing_listens() -> None:
    """A closed port is not a reachable HTTP service (otel/EM probe)."""
    assert await services._http_responds("http://127.0.0.1:59999/") is False


@pytest.mark.anyio
async def test_mod_load_skips_when_prerequisite_failed() -> None:
    """The slow game spawn must be skipped (never launched) if a prerequisite check failed."""
    game_missing = CheckResult("Game binary", "fail", "not found")
    result = await command._mod_load_row(enabled=True, prerequisites=(game_missing,))
    assert result.status == "skip"
    assert "Game binary" in result.detail


@pytest.mark.anyio
async def test_mod_load_row_points_to_flag_when_disabled() -> None:
    """When --check-mod-load is off, the row is shown as a skip that names the flag (not
    hidden)."""
    result = await command._mod_load_row(enabled=False, prerequisites=())
    assert result.status == "skip"
    assert "--check-mod-load" in result.hint
