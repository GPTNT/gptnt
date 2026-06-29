"""Tests for the `gptnt run` pipeline.

`run` *composes* existing orchestration (doctor gate, spawn, in-process submit, monitor); the only
genuinely new logic is the seam between them. So this file covers the deterministic, infra-free
surface: the small env-builder helpers (observability/wandb), the roster cross-check, and
`run_pipeline`'s control flow (the gate, the defensive branches, and the resume/early-exit paths).

Everything external is mocked: `diagnose` is replaced with an async stub that hands back a hand-
built `DiagnoseResult`, resume is driven by `RunPlanResult.remaining_specs` (the gate's single
WandB query), and the real spawn/submit/monitor (`_spawn_submit_monitor`) is monkeypatched out so
NO subprocess, network, or wandb call ever happens. The infra it would drive is exercised by
running `gptnt run` directly.
"""

from __future__ import annotations

import functools
import types
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, ClassVar, cast

import pytest

from gptnt.cli.__main__ import build_app
from gptnt.cli.doctor.command import DiagnoseResult
from gptnt.cli.doctor.run_plan import RunPlanResult
from gptnt.cli.run import pipeline
from gptnt.cli.run.manifest import RunManifest
from gptnt.specification import PlayerSpec

from tests._cli_runner import invoke_cli

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence


def _manifest(**overrides: object) -> RunManifest:
    """Build the smallest valid manifest, allowing per-test field overrides."""
    payload: dict[str, object] = {
        "suites": ["single-pairwise-sync"],
        "rooms": 1,
        "players": [PlayerSpec(model="claude46")],
    }
    payload.update(overrides)
    return RunManifest.model_validate(payload)


def _spec(defuser: str = "claude46", expert: str | None = None) -> types.SimpleNamespace:
    """A stand-in spec: the pipeline only reads `.defuser_name` / `.expert_name`."""
    return types.SimpleNamespace(
        defuser_name=defuser, expert_name=expert, attempt_name="exp_attempt1"
    )


async def _record_spawn(
    calls: list[dict[str, object]],
    manifest: object,
    specs: object,
    env_base: object,
    output_dir: object,
    logs_dir: object,
    *,
    interactive: bool,
) -> None:
    """Record one `_spawn_submit_monitor` call instead of spawning anything."""
    calls.append(
        {
            "manifest": manifest,
            "specs": specs,
            "env_base": env_base,
            "output_dir": output_dir,
            "logs_dir": logs_dir,
            "interactive": interactive,
        }
    )


def _patch_spawn(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    """Replace the real spawn/submit/monitor with a stub that records each call's specs.

    Returns the call log; an empty list means spawn was never reached.
    """
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(pipeline, "_spawn_submit_monitor", functools.partial(_record_spawn, calls))
    return calls


async def _fixed_diagnose(
    result: DiagnoseResult, *_args: object, **_kwargs: object
) -> DiagnoseResult:
    """Async `diagnose` stub that always hands back a pre-built result."""
    return result


def _patch_diagnose(monkeypatch: pytest.MonkeyPatch, result: DiagnoseResult) -> None:
    """Patch the `diagnose` the pipeline imported into its namespace to return `result`."""
    monkeypatch.setattr(
        "gptnt.cli.run.pipeline.diagnose", functools.partial(_fixed_diagnose, result)
    )


def _patch_load_specs(monkeypatch: pytest.MonkeyPatch, specs: Sequence[object]) -> None:
    """Patch the disk-spec loader so the pipeline 'reads' the given specs without touching disk."""
    monkeypatch.setattr(
        "gptnt.cli.run.pipeline.load_specs_from_dir", lambda _directory: list(specs)
    )


async def _fail_if_diagnose_called(*_args: object, **_kwargs: object) -> object:
    """`diagnose` stub that fails the test if the gate is ever reached."""
    raise AssertionError("diagnose must not run when there are no specs on disk")


async def _noop(*_args: object, **_kwargs: object) -> None:
    """No-op async stub for the spawn/monitor seams."""


async def _boom(*_args: object, **_kwargs: object) -> None:
    """Async stub that simulates an in-process submit failure."""
    raise RuntimeError("EM rejected the specs")


@asynccontextmanager
async def _fake_signals(_orch: object) -> AsyncIterator[None]:
    """No-op replacement for the signal-handling context manager."""
    yield


class _FakeOrch:
    """Stub `ProcessOrchestrator` that records whether the cluster was torn down."""

    terminate_calls: ClassVar[list[bool]] = []

    def __init__(self, **_kwargs: object) -> None:
        """Accept and ignore the real orchestrator's construction kwargs."""

    async def terminate_all(self) -> None:
        """Record that teardown was requested."""
        _FakeOrch.terminate_calls.append(True)


# -------------------------------------------------------------------------------------------------
# _observability_env
# -------------------------------------------------------------------------------------------------


def test_observability_env_full_is_empty() -> None:
    assert pipeline._observability_env("full") == {}


def test_observability_env_limited_keeps_pydantic_ai_on() -> None:
    env = pipeline._observability_env("limited")
    assert env["OBSERVABILITY_INSTRUMENT_FASTAPI"] == "false"
    assert env["OBSERVABILITY_INSTRUMENT_PYDANTIC_AI"] == "true"


def test_observability_env_off_disables_everything() -> None:
    env = pipeline._observability_env("off")
    # The PYDANTIC_AI flag is what distinguishes "off" (false) from "limited" (true).
    assert env["OBSERVABILITY_INSTRUMENT_PYDANTIC_AI"] == "false"
    assert env["OBSERVABILITY_ENABLE_METRICS"] == "false"
    assert all(
        value == "false"
        for key, value in env.items()
        if key.startswith("OBSERVABILITY_INSTRUMENT_")
    )


# -------------------------------------------------------------------------------------------------
# _assert_roster_covers_specs
# -------------------------------------------------------------------------------------------------


def test_assert_roster_covers_specs_passes_when_all_players_present() -> None:
    specs = [_spec(defuser="claude46", expert="gemini3")]
    config_to_player = {"claude46": "claude46", "gemini-3": "gemini3"}
    # Every referenced player is in config_to_player.values() — must not raise.
    pipeline._assert_roster_covers_specs(specs, config_to_player)


def test_assert_roster_covers_specs_raises_on_missing_player() -> None:
    specs = [_spec(defuser="claude46", expert="ghost")]
    config_to_player = {"claude46": "claude46"}  # no entry resolves to "ghost"
    with pytest.raises(RuntimeError):
        pipeline._assert_roster_covers_specs(specs, config_to_player)


# -------------------------------------------------------------------------------------------------
# run_pipeline — control flow
# -------------------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_run_pipeline_gate_blocks_when_failed_without_force(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    specs: Sequence[object] = [_spec()]
    result = DiagnoseResult(
        failed=True,
        model_reports=[],
        run_plan=RunPlanResult(
            findings=[], specs=list(specs), config_to_player={"claude46": "claude46"}
        ),
    )
    _patch_diagnose(monkeypatch, result)
    _patch_load_specs(monkeypatch, specs)
    calls = _patch_spawn(monkeypatch)

    with pytest.raises(RuntimeError):
        await pipeline.run_pipeline(_manifest(), manifest_stem="m", force=False)

    assert calls == []  # the gate must abort before spawning anything


@pytest.mark.anyio
async def test_run_pipeline_force_proceeds_despite_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    specs = [_spec()]
    result = DiagnoseResult(
        failed=True,
        model_reports=[],
        run_plan=RunPlanResult(
            findings=[], specs=specs, config_to_player={"claude46": "claude46"}
        ),
    )
    _patch_diagnose(monkeypatch, result)
    _patch_load_specs(monkeypatch, specs)
    calls = _patch_spawn(monkeypatch)

    await pipeline.run_pipeline(_manifest(), manifest_stem="m", force=True)  # must not raise

    assert len(calls) == 1


@pytest.mark.anyio
async def test_run_pipeline_aborts_when_run_plan_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    result = DiagnoseResult(failed=False, model_reports=[], run_plan=None)
    _patch_diagnose(monkeypatch, result)
    _patch_load_specs(monkeypatch, [_spec()])
    calls = _patch_spawn(monkeypatch)

    with pytest.raises(RuntimeError):
        await pipeline.run_pipeline(_manifest(), manifest_stem="m")

    assert calls == []


@pytest.mark.anyio
async def test_run_pipeline_aborts_when_no_specs_on_disk(monkeypatch: pytest.MonkeyPatch) -> None:
    """An absent/empty spec dir is a hard error before anything is gated or spawned."""
    monkeypatch.setattr("gptnt.cli.run.pipeline.diagnose", _fail_if_diagnose_called)
    _patch_load_specs(monkeypatch, [])  # nothing generated yet
    calls = _patch_spawn(monkeypatch)

    with pytest.raises(RuntimeError):
        await pipeline.run_pipeline(_manifest(), manifest_stem="m")

    # The raising stub guarantees we exit before the doctor gate; nothing was spawned either.
    assert calls == []


@pytest.mark.anyio
async def test_run_pipeline_exits_cleanly_when_everything_already_done(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    specs = [_spec()]
    # Resume filtering dropped everything → remaining_specs is empty → return without spawning.
    result = DiagnoseResult(
        failed=False,
        model_reports=[],
        run_plan=RunPlanResult(
            findings=[], specs=specs, config_to_player={"claude46": "claude46"}, remaining_specs=[]
        ),
    )
    _patch_diagnose(monkeypatch, result)
    _patch_load_specs(monkeypatch, specs)
    calls = _patch_spawn(monkeypatch)

    await pipeline.run_pipeline(_manifest(), manifest_stem="m")  # must not raise

    assert calls == []


@pytest.mark.anyio
async def test_run_pipeline_happy_path_spawns_with_resolved_specs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec_a = _spec(defuser="claude46")
    spec_b = _spec(defuser="claude46", expert="claude46")
    specs = [spec_a, spec_b]
    result = DiagnoseResult(
        failed=False,
        model_reports=[],
        run_plan=RunPlanResult(
            findings=[],
            specs=specs,
            config_to_player={"claude46": "claude46"},
            remaining_specs=[spec_a],  # only the first remains after resume filtering
        ),
    )
    _patch_diagnose(monkeypatch, result)
    _patch_load_specs(monkeypatch, specs)
    calls = _patch_spawn(monkeypatch)

    await pipeline.run_pipeline(_manifest(displays=[0, 1]), manifest_stem="m")

    assert len(calls) == 1
    # The threaded remaining set (not the full union) is what runs.
    assert calls[0]["specs"] == [spec_a]
    # The manifest (carrying display placement) is threaded through to the spawn seam.
    assert cast("RunManifest", calls[0]["manifest"]).displays == [0, 1]


# -------------------------------------------------------------------------------------------------
# _spawn_submit_monitor — teardown on submit failure
# -------------------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_spawn_submit_monitor_tears_down_on_submit_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """A failed in-process submit must terminate the spawned cluster, not orphan it."""
    _FakeOrch.terminate_calls.clear()

    monkeypatch.setattr("gptnt.cli.run.pipeline.ProcessOrchestrator", _FakeOrch)
    monkeypatch.setattr("gptnt.cli.run.pipeline.monitor_status", _noop)
    monkeypatch.setattr("gptnt.cli.run.pipeline.spawn_experiment_manager", _noop)
    monkeypatch.setattr("gptnt.cli.run.pipeline.spawn_rooms", _noop)
    monkeypatch.setattr("gptnt.cli.run.pipeline.spawn_players", _noop)
    monkeypatch.setattr("gptnt.cli.run.pipeline.handle_signals", _fake_signals)
    monkeypatch.setattr("gptnt.cli.run.pipeline.send_experiments", _boom)
    monkeypatch.setattr(
        "gptnt.common.paths.remove_empty_experiment_recorder_outputs", lambda _path: None
    )

    with pytest.raises(RuntimeError):
        await pipeline._spawn_submit_monitor(
            _manifest(), [_spec()], {"PYTHONUNBUFFERED": "1"}, tmp_path / "out", tmp_path / "logs"
        )

    assert _FakeOrch.terminate_calls == [True]  # the cluster was torn down on submit failure


# -------------------------------------------------------------------------------------------------
# CLI: the `run` command's real cyclopts parse path (help + declarative path validation).
# -------------------------------------------------------------------------------------------------


def test_run_help_through_cli() -> None:
    """`gptnt run --help` parses and documents its flags (lazy `--help` stays green)."""
    result = invoke_cli(build_app(), ["run", "--help"])
    assert result.exit_code == 0
    assert "--force" in result.output  # the run gate's --force stays (distinct from `new`'s)


def test_run_missing_manifest_path_rejected_by_cli() -> None:
    """A non-existent run.yaml is rejected by cyclopts' `ExistingFile` type (no bespoke error)."""
    result = invoke_cli(build_app(), ["run", "this_path_does_not_exist.yaml"])
    assert result.exit_code != 0
