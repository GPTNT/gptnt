"""Tests for the `gptnt run` pipeline and the public score-producing integrity gates.

The public-boundary group uses `invoke_cli` and stops each command before its first write or spawn.
The remaining tests cover the run pipeline's deterministic control flow, roster check, resume
handling, environment construction, and process teardown without starting subprocesses or making
network requests.
"""

from __future__ import annotations

import functools
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import TYPE_CHECKING, ClassVar, cast

import pytest

from gptnt.cli import integrity
from gptnt.cli.__main__ import build_app
from gptnt.cli.doctor import command as doctor_command
from gptnt.cli.doctor.command import DiagnoseResult
from gptnt.cli.doctor.run_plan import RunPlanResult
from gptnt.cli.onboarding import generate_specs as generate_command
from gptnt.cli.run import pipeline
from gptnt.cli.run.manifest import RunManifest
from gptnt.cli.statics import _evaluation as statics_evaluation
from gptnt.cli.submission import new as submission_new
from gptnt.cli.suite import __main__ as suite_command
from gptnt.experiments.suite.lock import SuiteLock
from gptnt.players.specification import PlayerProtocol, PlayerSpec
from gptnt.provenance import Provenance
from gptnt.statics import run as statics_run, run_metadata

from tests._cli_runner import invoke_cli
from tests._factories.experiments import make_experiment_spec

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence

    from gptnt.experiments.spec import ExperimentSpec


def _manifest(**overrides: object) -> RunManifest:
    """Build the smallest valid manifest, allowing per-test field overrides."""
    payload: dict[str, object] = {
        "suites": ["single-pairwise-sync"],
        "rooms": 1,
        "players": [PlayerSpec(player="claude-sonnet-4-6")],
    }
    payload.update(overrides)
    return RunManifest.model_validate(payload)


def _spec(defuser: str = "claude-sonnet-4-6", expert: str | None = None) -> ExperimentSpec:
    """A real spec keyed on the given player names (the pipeline reads the name fields)."""
    spec = make_experiment_spec()
    if expert is None:
        return spec.model_copy(update={"defuser_name": defuser})
    return spec.model_copy(
        update={
            "defuser_protocol": PlayerProtocol(
                role="defuser",
                communication_style="sync",
                is_playing_alone=False,
                include_manual=False,
            ),
            "defuser_name": defuser,
            "expert_protocol": PlayerProtocol(
                role="expert",
                communication_style="sync",
                is_playing_alone=False,
                include_manual=False,
            ),
            "expert_name": expert,
        }
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


def _unexpected_effect(*_args: object, **_kwargs: object) -> None:
    raise AssertionError("the integrity gate must run before the command's first effect")


def _fixed_statics_identity(
    _cls: type[run_metadata.StaticsIdentity],
    *,
    task_name: str,
    hf_repo_id: str,
    dataset_split: str | None,
    revision: str | None,
) -> run_metadata.StaticsIdentity:
    return run_metadata.StaticsIdentity(
        task_name=task_name,
        hf_repo_id=hf_repo_id,
        dataset_split=dataset_split,
        requested_revision=revision,
        resolved_revision="a1b2c3d4e5f6",
    )


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


@pytest.mark.anyio
async def test_run_force_does_not_bypass_roster_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    specs = [_spec(defuser="claude-sonnet-4-6", expert="ghost")]
    diagnosis = DiagnoseResult(
        failed=True,
        benchmark_failed=False,
        player_reports=[],
        run_plan=RunPlanResult(
            findings=[], specs=specs, config_to_player={"claude-sonnet-4-6": "claude-sonnet-4-6"}
        ),
    )
    _patch_diagnose(monkeypatch, diagnosis)
    _patch_load_specs(monkeypatch, specs)
    calls = _patch_spawn(monkeypatch)

    with pytest.raises(RuntimeError, match="roster does not cover"):
        await pipeline.run_pipeline(_manifest(), manifest_stem="m", force=True)

    assert calls == []


# -------------------------------------------------------------------------------------------------
# run_pipeline — control flow
# -------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "entry_point",
    [
        "suite-freeze",
        "doctor",
        "generate",
        "run-force",
        "statics-throw",
        "submission-new",
        "submission-validate",
    ],
)
def test_score_producing_commands_fail_integrity_before_writing_or_spawning(
    entry_point: str, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Each public command fails integrity before its first write or process spawn."""
    monkeypatch.setattr(
        integrity,
        "check_benchmark_integrity",
        lambda _repository: SimpleNamespace(
            release_tag="v2.0.0",
            release_commit="abc123456789",
            protected_changes=("src/gptnt/prompts/manual.py",),
            untracked_protected_files=(),
            permitted_input_changes=(),
            protected_content_modified=True,
        ),
    )
    monkeypatch.setattr(doctor_command, "_infrastructure_checks", _unexpected_effect)
    monkeypatch.setattr(doctor_command, "check_machine", _unexpected_effect)
    monkeypatch.setattr(suite_command, "_finish_write", _unexpected_effect)
    monkeypatch.setattr(generate_command, "write_specs_to_dir", _unexpected_effect)
    monkeypatch.setattr(statics_evaluation, "ConfigLoader", _unexpected_effect)
    monkeypatch.setattr(submission_new, "gather_experiments_for_suite", _unexpected_effect)
    monkeypatch.setattr(SuiteLock, "from_lock_path", _unexpected_effect)
    monkeypatch.setattr(pipeline, "load_specs_from_dir", lambda _directory: [_spec()])
    monkeypatch.setattr(pipeline, "_spawn_submit_monitor", _unexpected_effect)

    if entry_point == "submission-validate":
        _ = (tmp_path / "submission.yaml").write_text("")

    manifest = "runs/quickstart.yaml"
    argv = {
        "suite-freeze": ["suite", "freeze"],
        "doctor": ["doctor", manifest, "--check-mod-load"],
        "generate": ["generate", manifest, "--output-dir", str(tmp_path / "specs")],
        "run-force": ["run", manifest, "--force"],
        "statics-throw": ["statics", "expert-vqa-no-manual", "--player", "test-random", "--throw"],
        "submission-new": [
            "submission",
            "new",
            str(tmp_path / "experiments.duckdb"),
            "--output-dir",
            str(tmp_path / "submissions"),
        ],
        "submission-validate": ["submission", "validate", str(tmp_path)],
    }[entry_point]

    if entry_point == "submission-validate":
        result = invoke_cli(build_app(), argv)
        assert result.exit_code == 1
        assert "Protected content" in result.output
    else:
        with pytest.raises(RuntimeError):
            _ = invoke_cli(build_app(), argv)

    assert not (tmp_path / "specs").exists()
    assert not (tmp_path / "submissions").exists()


def test_unavailable_contributor_override_keeps_modified_benchmark_fatal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        integrity,
        "check_benchmark_integrity",
        lambda _repository: SimpleNamespace(
            release_tag="v2.0.0",
            release_commit="abc123456789",
            protected_changes=("src/gptnt/prompts/manual.py",),
            untracked_protected_files=(),
            permitted_input_changes=(),
            protected_content_modified=True,
        ),
    )

    diagnosis = integrity.diagnose_benchmark_integrity(
        allow_modified_benchmark=True, contributor_override_available=False, render=False
    )

    assert diagnosis.failed is True
    assert diagnosis.findings[-1].status == "fail"


def test_statics_contributor_override_warns_and_stamps_modified_provenance(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setattr(
        integrity,
        "check_benchmark_integrity",
        lambda _repository: SimpleNamespace(
            release_tag="v2.0.0",
            release_commit="abc123456789",
            protected_changes=("src/gptnt/prompts/manual.py",),
            untracked_protected_files=(),
            permitted_input_changes=("configs/player/test-random.yaml",),
            protected_content_modified=True,
        ),
    )
    modified_provenance = Provenance(
        gptnt_version="2.0.0",
        release_commit="abc123456789",
        release_tag="v2.0.0",
        protected_content_modified=True,
    )
    monkeypatch.setattr(Provenance, "capture", classmethod(lambda _cls: modified_provenance))
    monkeypatch.setattr(statics_run, "paths", SimpleNamespace(output=tmp_path))
    monkeypatch.setattr(
        run_metadata.StaticsIdentity, "resolve", classmethod(_fixed_statics_identity)
    )
    monkeypatch.setattr(statics_run.RunEvaluation, "throw", _noop)

    result = invoke_cli(
        build_app(),
        [
            "statics",
            "expert-vqa-no-manual",
            "--player",
            "test-random",
            "--throw",
            "--allow-modified-benchmark",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "WARNING: protected benchmark content is modified" in result.output
    metadata_path = next(tmp_path.rglob("run_meta.json"))
    metadata = run_metadata.StaticsRunMetadata.model_validate_json(metadata_path.read_text())
    assert metadata.provenance.protected_content_modified is True


@pytest.mark.anyio
async def test_run_pipeline_gate_blocks_when_failed_without_force(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    specs: Sequence[object] = [_spec()]
    result = DiagnoseResult(
        failed=True,
        benchmark_failed=False,
        player_reports=[],
        run_plan=RunPlanResult(
            findings=[],
            specs=list(specs),
            config_to_player={"claude-sonnet-4-6": "claude-sonnet-4-6"},
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
        benchmark_failed=False,
        player_reports=[],
        run_plan=RunPlanResult(
            findings=[], specs=specs, config_to_player={"claude-sonnet-4-6": "claude-sonnet-4-6"}
        ),
    )
    _patch_diagnose(monkeypatch, result)
    _patch_load_specs(monkeypatch, specs)
    calls = _patch_spawn(monkeypatch)

    await pipeline.run_pipeline(_manifest(), manifest_stem="m", force=True)  # must not raise

    assert len(calls) == 1


@pytest.mark.anyio
async def test_run_pipeline_aborts_when_run_plan_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    result = DiagnoseResult(failed=False, benchmark_failed=False, player_reports=[], run_plan=None)
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
        benchmark_failed=False,
        player_reports=[],
        run_plan=RunPlanResult(
            findings=[],
            specs=specs,
            config_to_player={"claude-sonnet-4-6": "claude-sonnet-4-6"},
            remaining_specs=[],
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
    spec_a = _spec(defuser="claude-sonnet-4-6")
    spec_b = _spec(defuser="claude-sonnet-4-6", expert="claude-sonnet-4-6")
    specs = [spec_a, spec_b]
    result = DiagnoseResult(
        failed=False,
        benchmark_failed=False,
        player_reports=[],
        run_plan=RunPlanResult(
            findings=[],
            specs=specs,
            config_to_player={"claude-sonnet-4-6": "claude-sonnet-4-6"},
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
