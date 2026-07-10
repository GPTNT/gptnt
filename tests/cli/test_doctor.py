"""Tests for `gptnt doctor`.

Coverage is the deterministic, infra-free surface: the model-result mapping, the display-gating
logic, the small text/path helpers, the summary tally, and the two async paths that need neither
network nor a spawned game (a dummy model check, and the mod-load gate that must *skip* — not spawn
— when a prerequisite already failed). The infra checks themselves (Redis/EM/otel/game spawn) are
environment-dependent and verified by running `gptnt doctor` directly.
"""

from __future__ import annotations

import io
import sys

import pytest
from rich.console import Console

from gptnt.cli.__main__ import build_app
from gptnt.cli.check_result import CheckResult
from gptnt.cli.doctor import checks, command, render
from gptnt.cli.doctor.validation import ModelValidationResult

from tests._cli_runner import invoke_cli


def _quiet_console() -> Console:
    return Console(file=io.StringIO(), width=100)


def test_static_boxes_ok_is_exists_and_instantiates() -> None:
    outcome = ModelValidationResult("m", None, ok=True, resolved_model_name="vendor:thing")
    exists, instantiates, note = checks._static_boxes(outcome)
    assert (exists, instantiates) == ("pass", "pass")
    assert "vendor:thing" in note


def test_static_boxes_compose_fail_is_exists_fail() -> None:
    outcome = ModelValidationResult("m", None, ok=False, error_stage="compose", error="bad yaml")
    exists, instantiates, _ = checks._static_boxes(outcome)
    # A config that doesn't compose doesn't "exist"; instantiation can't even be attempted.
    assert (exists, instantiates) == ("fail", "skip")


def test_static_boxes_agent_fail_is_instantiate_fail() -> None:
    outcome = ModelValidationResult("m", None, ok=False, error_stage="agent", error="boom")
    exists, instantiates, _ = checks._static_boxes(outcome)
    assert (exists, instantiates) == ("pass", "fail")


def test_static_boxes_missing_credential_is_instantiate_fail() -> None:
    outcome = ModelValidationResult(
        "m",
        None,
        ok=True,
        missing_credential=True,
        error="Set the FOO_API_KEY environment variable",
    )
    exists, instantiates, note = checks._static_boxes(outcome)
    # An unset provider key composes but can't run, so the doctor fails it (not a warn).
    assert (exists, instantiates) == ("pass", "fail")
    # The note surfaces pydantic-ai's own message (which names the var) — no maintained map.
    assert "FOO_API_KEY" in note


def test_model_report_failed_only_on_fail_box() -> None:
    assert checks.PlayerReport("m", "pass", "fail", "skip").failed is True
    assert checks.PlayerReport("m", "pass", "warn", "skip").failed is False
    assert checks.PlayerReport("m", "pass", "pass", "skip").failed is False


def test_model_report_missing_credential_fails_the_run() -> None:
    # A missing-credential model instantiates as ✗, so the report (and the doctor run) fails.
    _, instantiates, _ = checks._static_boxes(
        ModelValidationResult("m", None, ok=True, missing_credential=True, error="set FOO")
    )
    assert checks.PlayerReport("m", "pass", instantiates, "skip").failed is True


def test_display_skipped_off_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    result = checks.check_display()
    assert result.status == "skip"


def test_display_fails_on_linux_without_display(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("DISPLAY", raising=False)
    result = checks.check_display()
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
    assert checks._nearest_existing(missing) == tmp_path


def test_render_report_runs_for_every_status() -> None:
    sections = {
        "All": [
            CheckResult(f"check-{status}", status) for status in ("pass", "fail", "warn", "skip")
        ]  # type: ignore[arg-type]
    }
    render.render_report(_quiet_console(), sections)  # does not raise


def test_render_players_runs() -> None:
    details = [
        checks.PlayerDetail(
            checks.PlayerReport("good", "pass", "pass", "skip", "resolves to x"),
            ModelValidationResult("good", None, ok=True, resolved_model_name="x"),
        ),
        checks.PlayerDetail(
            checks.PlayerReport("bad", "fail", "skip", "skip", "no yaml"),
            ModelValidationResult("bad", None, ok=False, error_stage="compose", error="no yaml"),
        ),
    ]
    render.render_players(_quiet_console(), details)  # does not raise


@pytest.mark.anyio
async def test_check_players_dummy_passes() -> None:
    """A dummy model needs no credential: exists + instantiates pass; live is ⊘ without --live."""
    matrix = await checks.check_players([("test-random", None)], live=False)
    assert len(matrix.reports) == 1
    report = matrix.reports[0]
    assert report.label == "test-random"
    assert (report.exists, report.instantiates, report.live) == ("pass", "pass", "skip")
    assert report.failed is False
    # The config→player_name mapping comes from the SAME validation, keyed by the config name.
    assert "test-random" in matrix.config_to_player


@pytest.mark.anyio
async def test_redis_ping_false_when_nothing_listens() -> None:
    """A closed port is not a reachable Redis (guards against reporting bare-port-open as ✓)."""
    assert await checks._redis_pings("127.0.0.1", 59999) is False


@pytest.mark.anyio
async def test_http_probe_false_when_nothing_listens() -> None:
    """A closed port is not a reachable HTTP service (otel/EM probe)."""
    assert await checks._http_responds("http://127.0.0.1:59999/") is False


@pytest.mark.anyio
async def test_check_em_port_runs_without_crashing() -> None:
    """The EM-port check reads its endpoint from the shared `RuntimeSettings` and returns a result.

    Regression guard: it previously imported a nonexistent `em_settings` symbol and raised on every
    invocation. It must produce a `CheckResult` naming the configured port (8085 by default).
    """
    result = await checks.check_em_port()
    assert isinstance(result, CheckResult)
    assert ":8085" in result.name


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


# -------------------------------------------------------------------------------------------------
# CLI: exercise the real cyclopts parse path (flag rejection, exit codes).


def test_doctor_help_through_cli() -> None:
    """`gptnt doctor --help` parses and lists the flags (the lazy `--help` path stays green)."""
    result = invoke_cli(build_app(), ["doctor", "--help"])
    assert result.exit_code == 0
    assert "--check-mod-load" in result.output


def test_doctor_missing_manifest_path_rejected_by_cli() -> None:
    """A non-existent run.yaml is rejected by cyclopts' own path validator (no bespoke error)."""
    result = invoke_cli(build_app(), ["doctor", "this_path_does_not_exist.yaml"])
    assert result.exit_code != 0
