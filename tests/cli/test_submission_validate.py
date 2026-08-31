"""Tests for `gptnt submission validate`, driven by a bundle built by the application writers.

A fully covering interactive bundle for the solo leaderboard suite is built once (one solved run
per mission in the suite's set), then each test copies and breaks exactly one thing. Success paths
go through the CLI. Failure paths call the command directly and assert the raised `RuntimeError`
(per `tests/_cli_runner.py`).
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest
import yaml
from pydantic_ai import RunUsage
from pydantic_core import from_json

from gptnt.cli.__main__ import build_app
from gptnt.cli.submission import _checks as submission_checks
from gptnt.cli.submission._bundle import (
    InteractiveBundle,
    StaticsBundle,
    load_submission_bundle,
    slugify,
)
from gptnt.cli.submission._schema import SubmissionExperiment
from gptnt.cli.submission.validate import validate_submission
from gptnt.experiments.db.typed_parquet import read_typed_parquet, write_typed_parquet
from gptnt.experiments.records import ExperimentSummary
from gptnt.experiments.suite.compose import compose_suite
from gptnt.experiments.suite.lock import SuiteLock
from gptnt.players.specification import PlayerCapabilities, PlayerProtocol
from gptnt.provenance import BenchmarkIntegrityError

from tests._cli_runner import invoke_cli
from tests._factories.experiments import (
    make_experiment_instance,
    make_experiment_spec,
    make_provenance,
    make_solved_bomb,
)
from tests._factories.statics import write_statics_run

if TYPE_CHECKING:
    from pathlib import Path

    from gptnt.experiments.suite.definition import Suite
    from gptnt.ktane.mission_spec import KtaneMissionSpec

SUITE = "single-parametric-sync"


def _make_experiment(
    mission: KtaneMissionSpec, suite: Suite, suite_digest: str
) -> SubmissionExperiment:
    """One valid, solved run of `mission` recorded against `suite`."""
    spec = make_experiment_spec(seed=mission.seed).model_copy(
        update={
            "mission_spec": mission,
            "mission_set": suite.mission_set,
            "suite_name": suite.name,
            "suite_revision": suite.revision,
            "suite_digest": suite_digest,
            "manual_profile": suite.manual_profile,
        }
    )
    summary = ExperimentSummary.from_instance_and_bomb_state(
        instance=make_experiment_instance(spec),
        final_bomb_state=make_solved_bomb(),
        is_hard_crash=False,
        provenance=make_provenance(),
    )
    return SubmissionExperiment.from_summary(
        summary=summary, final_bomb_state=make_solved_bomb(), usage_by_role={"defuser": RunUsage()}
    )


def _read_manifest(bundle_dir: Path) -> dict[str, Any]:
    return yaml.safe_load((bundle_dir / "submission.yaml").read_text())


def _write_manifest(bundle_dir: Path, manifest: dict[str, Any]) -> None:
    _ = (bundle_dir / "submission.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False))


def _fill_submitter(bundle_dir: Path) -> None:
    manifest = _read_manifest(bundle_dir)
    manifest["submitter"] = {"name": "Ada Lovelace", "contact": "@ada", "affiliation": None}
    _write_manifest(bundle_dir, manifest)


@pytest.fixture(scope="module")
def suite() -> Suite:
    return compose_suite(SUITE)


@pytest.fixture(scope="module")
def suite_snapshot(suite: Suite) -> SuiteLock:
    return SuiteLock.from_lock_path().snapshot(suite.name, suite.revision)


@pytest.fixture(scope="module")
def valid_bundle_root(
    tmp_path_factory: pytest.TempPathFactory, suite: Suite, suite_snapshot: SuiteLock
) -> Path:
    """A submissions root holding one fully covering, submitter-filled interactive bundle."""
    root = tmp_path_factory.mktemp("submissions")
    frozen_suite, missions = suite_snapshot.load_suite(suite.name, suite.revision)
    suite_digest = suite_snapshot.suites[0].suite_digest
    experiments = [_make_experiment(mission, frozen_suite, suite_digest) for mission in missions]
    _fill_submitter(InteractiveBundle.from_experiments(experiments, suite_snapshot).save(root))
    return root


@pytest.fixture
def bundle_copy(valid_bundle_root: Path, tmp_path: Path) -> Path:
    """A fresh mutable copy of the valid bundle tree.

    Return the bundle dir itself.
    """
    root = tmp_path / "submissions"
    _ = shutil.copytree(valid_bundle_root, root)
    return next(root.rglob("submission.yaml")).parent


def _assert_validate_fails(path: Path) -> None:
    """A failing validation exits non-zero (the command `sys.exit(1)`s on any failed check)."""
    with pytest.raises(SystemExit) as exit_info:
        validate_submission(path)
    assert exit_info.value.code == 1


def _unwrap_output(capsys: pytest.CaptureFixture[str]) -> str:
    """The output is whitespace-collapsed.

    Assert on `✗ <check-name>`, which never wraps.
    """
    return " ".join(capsys.readouterr().out.split())


def test_bundle_round_trips_through_save_and_load(bundle_copy: Path) -> None:
    loaded = load_submission_bundle(bundle_copy)
    assert isinstance(loaded, InteractiveBundle)
    suite_name = loaded.manifest.target.partition("@")[0]
    assert slugify(suite_name) in bundle_copy.name
    assert len(loaded.experiments) == len(
        read_typed_parquet(SubmissionExperiment, bundle_copy / "experiments.parquet")
    )
    # Saving what was loaded reproduces the same directory (submitter edits survive the merge).
    assert loaded.save(bundle_copy.parent) == bundle_copy
    assert _read_manifest(bundle_copy)["submitter"]["name"] == "Ada Lovelace"


def test_valid_bundle_passes(bundle_copy: Path) -> None:
    assert _read_manifest(bundle_copy)["schema_version"] == 4
    result = invoke_cli(build_app(), ["submission", "validate", str(bundle_copy)])
    assert result.exit_code == 0, result.output
    assert "✗" not in result.output
    assert "1 ok, 0 failed" in result.output


def test_development_package_version_can_match_release_content(bundle_copy: Path) -> None:
    payload_path = bundle_copy / "experiments.parquet"
    experiments = read_typed_parquet(SubmissionExperiment, payload_path)
    development_version = "2.0.1.dev3+gabc1234"
    write_typed_parquet(
        [
            experiment.model_copy(update={"gptnt_version": development_version})
            for experiment in experiments
        ],
        file_path=payload_path,
    )
    manifest = _read_manifest(bundle_copy)
    manifest["provenance"]["gptnt_version"] = development_version
    _write_manifest(bundle_copy, manifest)

    result = invoke_cli(
        build_app(), ["submission", "validate", str(bundle_copy), "--format", "json"]
    )

    assert result.exit_code == 0, result.output


def test_checkout_digest_mismatch_fails_protected_content(bundle_copy: Path) -> None:
    payload_path = bundle_copy / "experiments.parquet"
    experiments = read_typed_parquet(SubmissionExperiment, payload_path)
    mismatch = {
        "protected_content_digest": f"sha256:{'2' * 64}",
        "protected_content_modified": True,
    }
    write_typed_parquet(
        [experiment.model_copy(update=mismatch) for experiment in experiments],
        file_path=payload_path,
    )
    manifest = _read_manifest(bundle_copy)
    manifest["provenance"].update(mismatch)
    _write_manifest(bundle_copy, manifest)

    result = invoke_cli(
        build_app(), ["submission", "validate", str(bundle_copy), "--format", "json"]
    )

    assert result.exit_code == 1
    checks = from_json(result.output)["bundles"][0]["checks"]
    assert any(
        check["name"] == "protected content" and check["status"] == "fail" for check in checks
    )


def test_bundle_snapshot_must_match_the_installed_suite_registry(bundle_copy: Path) -> None:
    """A self-consistent snapshot is rejected when it differs from the installed registry."""
    snapshot_path = bundle_copy / "suite.lock"
    snapshot = SuiteLock.from_lock_path(snapshot_path)
    altered_entry = snapshot.suites[0].model_copy(update={"frozen_at": "2026-08-25T00:00:00Z"})
    snapshot.model_copy(update={"suites": (altered_entry,)}).dump_to_path(snapshot_path)

    result = invoke_cli(
        build_app(), ["submission", "validate", "--require-installed-lock-match", str(bundle_copy)]
    )

    assert result.exit_code == 1
    assert "installed suite registry" in result.output


def test_installed_release_to_match_bundle_uses_declared_identity_and_package_repository(
    bundle_copy: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = _read_manifest(bundle_copy)
    expected_digest = manifest["provenance"]["release_protected_content_digest"]
    received: list[tuple[Path, str, str]] = []

    def recompute(  # noqa: WPS430
        repository: Path, *, release_tag: str, release_commit: str
    ) -> str:
        received.append((repository, release_tag, release_commit))
        return expected_digest

    monkeypatch.setattr(submission_checks, "compute_release_protected_content_digest", recompute)
    monkeypatch.chdir(tmp_path)

    result = invoke_cli(
        build_app(),
        [
            "submission",
            "validate",
            "--require-installed-release-to-match-bundle",
            str(bundle_copy),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "installed suite registry" not in result.output
    assert received == [
        (
            received[0][0],
            manifest["provenance"]["release_tag"],
            manifest["provenance"]["release_commit"],
        )
    ]
    assert "src/gptnt/cli/submission" in received[0][0].as_posix()


def test_installed_release_digest_mismatch_is_reported(bundle_copy: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        submission_checks,
        "compute_release_protected_content_digest",
        lambda *_args, **_kwargs: f"sha256:{'2' * 64}",
    )

    result = invoke_cli(
        build_app(),
        [
            "submission",
            "validate",
            "--require-installed-release-to-match-bundle",
            str(bundle_copy),
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 1
    checks = from_json(result.output)["bundles"][0]["checks"]
    finding = next(
        check for check in checks if check["name"] == "installed release protected content"
    )
    assert finding["status"] == "fail"
    assert "sha256:111111111111" in finding["detail"]
    assert "sha256:222222222222" in finding["detail"]


def test_installed_release_requires_source_git_metadata(bundle_copy: Path, monkeypatch) -> None:
    def unavailable(*_args: object, **_kwargs: object) -> str:  # noqa: WPS430
        raise BenchmarkIntegrityError("installed package is not a Git repository")

    monkeypatch.setattr(submission_checks, "compute_release_protected_content_digest", unavailable)

    result = invoke_cli(
        build_app(),
        [
            "submission",
            "validate",
            "--require-installed-release-to-match-bundle",
            str(bundle_copy),
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 1
    checks = from_json(result.output)["bundles"][0]["checks"]
    finding = next(
        check for check in checks if check["name"] == "installed release protected content"
    )
    assert finding["status"] == "fail"
    assert "source Git metadata" in finding["detail"]


def test_installed_release_reports_unreadable_git_metadata(bundle_copy: Path, monkeypatch) -> None:
    def unreadable(*_args: object, **_kwargs: object) -> str:  # noqa: WPS430
        raise OSError("cannot read Git objects")

    monkeypatch.setattr(submission_checks, "compute_release_protected_content_digest", unreadable)

    result = invoke_cli(
        build_app(),
        [
            "submission",
            "validate",
            "--require-installed-release-to-match-bundle",
            str(bundle_copy),
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 1
    checks = from_json(result.output)["bundles"][0]["checks"]
    finding = next(
        check for check in checks if check["name"] == "installed release protected content"
    )
    assert finding["status"] == "fail"
    assert "cannot read Git objects" in finding["detail"]


def test_bundle_with_a_self_consistent_unaccepted_suite_is_rejected(
    bundle_copy: Path, tmp_path: Path
) -> None:
    """Installed-registry validation rejects a bundle that rewrites its suite identity fields."""
    bundle = load_submission_bundle(bundle_copy)
    assert isinstance(bundle, InteractiveBundle)
    unaccepted_name, unaccepted_revision = "unaccepted-suite", 9
    entry = bundle.suite_lock.suites[0].model_copy(
        update={"name": unaccepted_name, "revision": unaccepted_revision}
    )
    unaccepted_lock = bundle.suite_lock.model_copy(update={"suites": (entry,)})
    unaccepted_experiments = [
        experiment.model_copy(
            update={"suite_name": unaccepted_name, "suite_revision": unaccepted_revision}
        )
        for experiment in bundle.experiments
    ]
    unaccepted_bundle = InteractiveBundle.from_experiments(
        unaccepted_experiments, unaccepted_lock, submitter=bundle.manifest.submitter
    )
    unaccepted_path = unaccepted_bundle.save(tmp_path / "unaccepted")

    local_result = invoke_cli(build_app(), ["submission", "validate", str(unaccepted_path)])
    release_result = invoke_cli(
        build_app(),
        ["submission", "validate", "--require-installed-lock-match", str(unaccepted_path)],
    )

    assert local_result.exit_code == 0, local_result.output
    assert release_result.exit_code == 1
    assert "installed suite registry" in release_result.output


def test_installed_lock_check_reports_empty_suite_snapshot(bundle_copy: Path) -> None:
    snapshot_path = bundle_copy / "suite.lock"
    snapshot = SuiteLock.from_lock_path(snapshot_path)
    snapshot.model_copy(update={"suites": ()}).dump_to_path(snapshot_path)

    result = invoke_cli(
        build_app(),
        [
            "submission",
            "validate",
            "--require-installed-lock-match",
            str(bundle_copy),
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 1
    checks = from_json(result.output)["bundles"][0]["checks"]
    assert any(check["name"] == "suite snapshot" and check["status"] == "fail" for check in checks)


@pytest.mark.parametrize(
    ("identity_domain", "expected_check"),
    [("release", "provenance"), ("player", "player fingerprint"), ("suite", "suite digest")],
)
def test_identity_disagreement_fails(
    bundle_copy: Path, identity_domain: str, expected_check: str
) -> None:
    """One representative disagreement in each identity domain is rejected."""
    manifest = _read_manifest(bundle_copy)
    if identity_domain == "release":
        manifest["provenance"]["release_tag"] = "v2.0.1"
    elif identity_domain == "player":
        manifest["players"][0]["capabilities"]["model_settings"] = {"temperature": 0.25}
    else:
        manifest["measured"]["suite_digest"] = "deadbeef"
    _write_manifest(bundle_copy, manifest)

    result = invoke_cli(
        build_app(), ["submission", "validate", str(bundle_copy), "--format", "json"]
    )
    assert result.exit_code == 1
    checks = from_json(result.output)["bundles"][0]["checks"]
    assert any(check["name"] == expected_check and check["status"] == "fail" for check in checks)


def test_schema_v1_stops_at_version_boundary(bundle_copy: Path) -> None:
    manifest = _read_manifest(bundle_copy)
    manifest["schema_version"] = 1
    manifest["measured"] = "v1 content must not be parsed"
    _write_manifest(bundle_copy, manifest)

    result = invoke_cli(
        build_app(), ["submission", "validate", str(bundle_copy), "--format", "json"]
    )
    assert result.exit_code == 1
    checks = from_json(result.output)["bundles"][0]["checks"]
    assert len(checks) == 1
    assert checks[0]["name"] == "schema_version"
    assert "schema-v1 submissions are not supported" in checks[0]["detail"]


def test_missing_schema_version_stops_at_version_boundary(bundle_copy: Path) -> None:
    manifest = _read_manifest(bundle_copy)
    _ = manifest.pop("schema_version")
    manifest["measured"] = "unversioned content must not be parsed"
    _write_manifest(bundle_copy, manifest)

    result = invoke_cli(
        build_app(), ["submission", "validate", str(bundle_copy), "--format", "json"]
    )
    assert result.exit_code == 1
    checks = from_json(result.output)["bundles"][0]["checks"]
    assert len(checks) == 1
    assert checks[0]["name"] == "schema_version"
    assert "schema_version is required" in checks[0]["detail"]


def test_modified_benchmark_records_cannot_be_submitted(
    bundle_copy: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = bundle_copy / "experiments.parquet"
    experiments = read_typed_parquet(SubmissionExperiment, payload)
    write_typed_parquet(
        [
            experiment.model_copy(
                update={
                    "protected_content_digest": f"sha256:{'2' * 64}",
                    "protected_content_modified": True,
                }
            )
            for experiment in experiments
        ],
        file_path=payload,
    )
    manifest = _read_manifest(bundle_copy)
    manifest["provenance"].update(
        {"protected_content_digest": f"sha256:{'2' * 64}", "protected_content_modified": True}
    )
    _write_manifest(bundle_copy, manifest)

    _assert_validate_fails(bundle_copy)
    assert "✗ protected content" in _unwrap_output(capsys)


def test_records_without_release_provenance_cannot_be_submitted(bundle_copy: Path) -> None:
    payload = bundle_copy / "experiments.parquet"
    experiments = read_typed_parquet(SubmissionExperiment, payload)
    missing = {
        "release_commit": None,
        "release_tag": None,
        "release_protected_content_digest": None,
        "protected_content_digest": None,
        "protected_content_modified": None,
    }
    write_typed_parquet(
        [experiment.model_copy(update=missing) for experiment in experiments], file_path=payload
    )
    manifest = _read_manifest(bundle_copy)
    manifest["provenance"].update(missing)
    _write_manifest(bundle_copy, manifest)

    result = invoke_cli(
        build_app(), ["submission", "validate", str(bundle_copy), "--format", "json"]
    )

    assert result.exit_code == 1
    checks = from_json(result.output)["bundles"][0]["checks"]
    assert checks[0]["name"] == "manifest"
    assert "submission schema 4 requires protected-content digests" in checks[0]["detail"]


def test_missing_mission_fails(bundle_copy: Path, capsys: pytest.CaptureFixture[str]) -> None:
    experiments = read_typed_parquet(SubmissionExperiment, bundle_copy / "experiments.parquet")
    write_typed_parquet(experiments[1:], file_path=bundle_copy / "experiments.parquet")

    _assert_validate_fails(bundle_copy)
    assert "✗ missing" in _unwrap_output(capsys)


def test_duplicate_mission_fails(bundle_copy: Path, capsys: pytest.CaptureFixture[str]) -> None:
    experiments = read_typed_parquet(SubmissionExperiment, bundle_copy / "experiments.parquet")
    write_typed_parquet(
        [*experiments, experiments[0]], file_path=bundle_copy / "experiments.parquet"
    )

    _assert_validate_fails(bundle_copy)
    assert "✗ duplicates" in _unwrap_output(capsys)


def test_unknown_mission_fails(bundle_copy: Path, capsys: pytest.CaptureFixture[str]) -> None:
    experiments = read_typed_parquet(SubmissionExperiment, bundle_copy / "experiments.parquet")
    original = experiments[0]
    foreign_seed = 999_999_999
    foreign_mission = original.mission_spec.model_copy(update={"seed": foreign_seed})
    foreign = original.model_copy(update={"mission_spec": foreign_mission})
    write_typed_parquet([*experiments[1:], foreign], file_path=bundle_copy / "experiments.parquet")

    _assert_validate_fails(bundle_copy)
    assert "✗ unknown" in _unwrap_output(capsys)


def test_invalid_run_fails(bundle_copy: Path, capsys: pytest.CaptureFixture[str]) -> None:
    experiments = read_typed_parquet(SubmissionExperiment, bundle_copy / "experiments.parquet")
    crashed = experiments[0].model_copy(update={"is_hard_crash": True})
    write_typed_parquet([crashed, *experiments[1:]], file_path=bundle_copy / "experiments.parquet")

    _assert_validate_fails(bundle_copy)
    assert "✗ outcomes" in _unwrap_output(capsys)


def test_blank_submitter_fails(bundle_copy: Path) -> None:
    manifest = _read_manifest(bundle_copy)
    manifest["submitter"] = {"name": "", "contact": "", "affiliation": None}
    _write_manifest(bundle_copy, manifest)

    _assert_validate_fails(bundle_copy)


def test_renamed_model_dir_fails(bundle_copy: Path) -> None:
    renamed = bundle_copy.with_name("20200101_test-defuser_00000000_wrong-suite_9")
    _ = bundle_copy.rename(renamed)

    _assert_validate_fails(renamed)


def test_missing_payload_fails(bundle_copy: Path) -> None:
    (bundle_copy / "experiments.parquet").unlink()

    _assert_validate_fails(bundle_copy)


def test_sweep_reports_every_bundle(bundle_copy: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A root with one good and one broken bundle fails overall but renders both."""
    root = bundle_copy.parent
    broken = root / "broken"
    _ = shutil.copytree(bundle_copy, broken)  # the copy's dir no longer matches its manifest

    _assert_validate_fails(root)
    assert "1 ok, 1 failed" in _unwrap_output(capsys)


def test_json_format_is_parseable(bundle_copy: Path) -> None:
    """`--format json` emits a summary and every check as machine-readable JSON."""
    result = invoke_cli(
        build_app(), ["submission", "validate", str(bundle_copy), "--format", "json"]
    )
    assert result.exit_code == 0, result.output
    payload = from_json(result.output)
    assert payload["summary"] == {"total": 1, "ok": 1, "failed": 0}
    assert payload["bundles"][0]["ok"] is True
    names = {check["name"] for check in payload["bundles"][0]["checks"]}
    assert {"suite", "suite digest", "coverage"} <= names


def test_github_format_annotates_failures(
    bundle_copy: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--format github` emits a `::error` workflow annotation for each failed check."""
    experiments = read_typed_parquet(SubmissionExperiment, bundle_copy / "experiments.parquet")
    write_typed_parquet(experiments[1:], file_path=bundle_copy / "experiments.parquet")

    with pytest.raises(SystemExit) as exit_info:
        validate_submission(bundle_copy, report_format="github")
    assert exit_info.value.code == 1
    output = capsys.readouterr().out
    assert "::error title=" in output
    assert "missing" in output


# A pairwise suite plays each mission once per expert, so coverage is over (defuser, expert,
# mission) pairings rather than missions alone.
PAIRWISE_SUITE = "single-pairwise-sync"
PAIRWISE_EXPERTS = ("test-expert", "test-oracle")


def _make_pairwise_experiment(
    mission: KtaneMissionSpec, suite: Suite, suite_digest: str, expert_name: str
) -> SubmissionExperiment:
    """One valid, solved run of `mission` played by the defuser paired with `expert_name`."""
    experiment = _make_experiment(mission, suite, suite_digest)
    return experiment.model_copy(
        update={
            "defuser_protocol": experiment.defuser_protocol.model_copy(
                update={"is_playing_alone": False}
            ),
            "expert_name": expert_name,
            "expert_protocol": PlayerProtocol(
                role="expert",
                communication_style="sync",
                is_playing_alone=False,
                include_manual=True,
            ),
            "expert_uuid": uuid4(),
            "expert_capabilities": PlayerCapabilities(player_name=expert_name, player_type="ai"),
        }
    )


@pytest.fixture(scope="module")
def pairwise_suite() -> Suite:
    return compose_suite(PAIRWISE_SUITE)


@pytest.fixture(scope="module")
def pairwise_snapshot(pairwise_suite: Suite) -> SuiteLock:
    return SuiteLock.from_lock_path().snapshot(pairwise_suite.name, pairwise_suite.revision)


@pytest.fixture(scope="module")
def valid_pairwise_root(
    tmp_path_factory: pytest.TempPathFactory, pairwise_suite: Suite, pairwise_snapshot: SuiteLock
) -> Path:
    """A submissions root with a covering pairwise bundle: every mission run once per expert."""
    root = tmp_path_factory.mktemp("pairwise-submissions")
    frozen_suite, missions = pairwise_snapshot.load_suite(
        pairwise_suite.name, pairwise_suite.revision
    )
    suite_digest = pairwise_snapshot.suites[0].suite_digest
    experiments = [
        _make_pairwise_experiment(mission, frozen_suite, suite_digest, expert)
        for mission in missions
        for expert in PAIRWISE_EXPERTS
    ]
    _fill_submitter(InteractiveBundle.from_experiments(experiments, pairwise_snapshot).save(root))
    return root


@pytest.fixture
def pairwise_bundle_copy(valid_pairwise_root: Path, tmp_path: Path) -> Path:
    """A fresh mutable copy of the covering pairwise bundle.

    Return the bundle dir itself.
    """
    root = tmp_path / "submissions"
    _ = shutil.copytree(valid_pairwise_root, root)
    return next(root.rglob("submission.yaml")).parent


def test_pairwise_bundle_passes(pairwise_bundle_copy: Path) -> None:
    """Each mission played once per expert is legitimate coverage, not duplicates."""
    result = invoke_cli(build_app(), ["submission", "validate", str(pairwise_bundle_copy)])
    assert result.exit_code == 0, result.output
    assert "✗" not in result.output


def test_pairwise_repeated_pairing_fails(
    pairwise_bundle_copy: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Repeated runs of the same (expert, mission) pairing are a duplicate."""
    payload = pairwise_bundle_copy / "experiments.parquet"
    experiments = read_typed_parquet(SubmissionExperiment, payload)
    write_typed_parquet([*experiments, experiments[0]], file_path=payload)

    _assert_validate_fails(pairwise_bundle_copy)
    assert "✗ duplicates" in _unwrap_output(capsys)


def _build_statics_bundle(
    tmp_path: Path,
    *,
    requested_revision: str | None = "v1",
    resolved_revision: str | None = "a1b2c3d4e5f6",
) -> Path:
    run_dir = write_statics_run(
        tmp_path / "statics",
        requested_revision=requested_revision,
        resolved_revision=resolved_revision,
    )
    bundle_dir = StaticsBundle.from_run_dir(run_dir).save(tmp_path / "submissions")
    _fill_submitter(bundle_dir)
    return bundle_dir


def test_valid_statics_bundle_passes(tmp_path: Path) -> None:
    bundle_dir = _build_statics_bundle(tmp_path)

    result = invoke_cli(build_app(), ["submission", "validate", str(bundle_dir)])
    assert result.exit_code == 0, result.output
    assert "✗" not in result.output


def test_unpinned_statics_dataset_warns_but_passes(tmp_path: Path) -> None:
    bundle_dir = _build_statics_bundle(tmp_path, requested_revision=None, resolved_revision=None)

    result = invoke_cli(build_app(), ["submission", "validate", str(bundle_dir)])
    assert result.exit_code == 0, result.output
    assert "⚠" in result.output


def test_corrupt_statics_metrics_fails(tmp_path: Path) -> None:
    bundle_dir = _build_statics_bundle(tmp_path)
    _ = (bundle_dir / "metrics.json").write_text("{not json")

    _assert_validate_fails(bundle_dir)


def test_empty_root_errors(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="No bundles under"):
        validate_submission(tmp_path)
