"""Tests for the generated leaderboard artifact command."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from pydantic_ai import RunUsage

from gptnt.cli.__main__ import build_app
from gptnt.cli.submission._bundle import InteractiveBundle
from gptnt.cli.submission._schema import (
    InteractiveSubmission,
    SubmissionExperiment,
    SubmissionPlayer,
    Submitter,
)
from gptnt.experiments.suite.compose import compose_suite
from gptnt.experiments.suite.definition import SuiteIdentity
from gptnt.experiments.suite.lock import SuiteLock
from gptnt.players.specification import PlayerIdentity

from tests._cli_runner import invoke_cli
from tests._factories.experiments import make_experiment_summary, make_solved_bomb

_ZERO_PERCENT = 0.00

if TYPE_CHECKING:
    from pathlib import Path


def test_build_writes_empty_artifact_when_no_eligible_bundles_exist(tmp_path: Path) -> None:
    output = tmp_path / "leaderboard.generated.json"

    result = invoke_cli(
        build_app(), ["leaderboard", "build", str(tmp_path), "--output", str(output)]
    )

    assert result.exit_code == 0, result.output
    assert json.loads(output.read_text()) == {
        "schema_version": 1,
        "generated_from": "local",
        "suites": {},
        "entries": [],
    }


def test_build_aggregates_only_active_randomised_manual_suites(tmp_path: Path) -> None:
    submissions_dir = tmp_path / "submissions"
    suite = compose_suite("multi-self-async")
    snapshot = SuiteLock.from_lock_path().snapshot(suite.name, suite.revision)
    measured = SuiteIdentity(
        suite_name=suite.name,
        suite_revision=suite.revision,
        suite_digest=snapshot.suites[0].suite_digest,
    )
    summary = make_experiment_summary(
        defuser_name="test-defuser", expert_name="test-expert", communication_style="async"
    ).model_copy(
        update={
            "suite_name": measured.suite_name,
            "suite_revision": measured.suite_revision,
            "suite_digest": measured.suite_digest,
        }
    )
    experiment = SubmissionExperiment.from_summary(
        summary=summary,
        final_bomb_state=make_solved_bomb(),
        usage_by_role={
            "defuser": RunUsage(input_tokens=12, output_tokens=8),
            "expert": RunUsage(input_tokens=3, output_tokens=2),
        },
    )
    defuser = SubmissionPlayer(
        role="defuser",
        capabilities=experiment.defuser_capabilities,
        identity=PlayerIdentity(
            display_name="Test Defuser", organisation="GPTNT", is_os_model=True, url=None
        ),
    )
    expert = SubmissionPlayer(
        role="expert",
        capabilities=experiment.expert_capabilities,
        identity=PlayerIdentity(
            display_name="Test Expert", organisation="GPTNT", is_os_model=True, url=None
        ),
    )
    manifest = InteractiveSubmission(
        submission_id="active-submission",
        measured=measured,
        submitter=Submitter(name="Ada", contact="@ada"),
        players=[defuser, expert],
        provenance=summary,
        run_date=summary.start_time,
    )
    _ = InteractiveBundle(manifest=manifest, experiments=[experiment], suite_lock=snapshot).save(
        submissions_dir
    )
    legacy_manifest = manifest.model_copy(
        update={
            "submission_id": "legacy-submission",
            "measured": measured.model_copy(update={"suite_revision": 1}),
        }
    )
    _ = InteractiveBundle(
        manifest=legacy_manifest, experiments=[experiment], suite_lock=snapshot
    ).save(submissions_dir)
    historical_bundle = submissions_dir / "historical-schema-v1"
    _ = historical_bundle.mkdir()
    _ = (historical_bundle / "submission.yaml").write_text(
        "schema_version: 1\nmeasured:\n  suite_name: multi-self-async\n  suite_revision: 1\n"
    )

    output = tmp_path / "leaderboard.generated.json"
    result = invoke_cli(
        build_app(), ["leaderboard", "build", str(tmp_path), "--output", str(output)]
    )

    assert result.exit_code == 0, result.output
    artifact = json.loads(output.read_text())
    assert artifact["suites"] == {
        measured.target: {
            "name": suite.name,
            "revision": suite.revision,
            "digest": measured.suite_digest,
            "communication_style": "async",
            "mission_set": suite.mission_set,
            "modality": list(suite.modality),
        }
    }
    assert [entry["submission_id"] for entry in artifact["entries"]] == ["active-submission"]
    assert artifact["entries"][0]["metrics"] == {
        "attempts": 1,
        "mission_solved_pct": 100.0,
        "module_solved_pct": _ZERO_PERCENT,
        "any_module_solved_pct": _ZERO_PERCENT,
        "mean_strikes": _ZERO_PERCENT,
        "timed_out_pct": _ZERO_PERCENT,
        "detonated_pct": _ZERO_PERCENT,
    }
    assert artifact["entries"][0]["usage"] == {
        "defuser_mean_tokens": 20.0,
        "expert_mean_tokens": 5.0,
    }
