"""End-to-end tests for `gptnt submission new`, driven off a real DuckDB built by the ingest path.

Records are written as recorder parquet, ingested into a temp `experiments.duckdb`, and the bundle
is built through the CLI. The human-only fields (submitter + declared system attribution) must be
blank on build and preserved across a rebuild.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import orjson
import pytest
import yaml
from pydantic_ai import RunUsage

from gptnt.cli.__main__ import build_app
from gptnt.cli.submission._schema import SubmissionExperiment
from gptnt.experiments.db.ingest import ingest_player_records
from gptnt.experiments.db.typed_parquet import read_typed_parquet
from gptnt.experiments.instance import ExperimentInstance
from gptnt.experiments.recorder.parquet import (
    blob_step,
    footer_from_player_record,
    write_player_record_parquet,
)
from gptnt.experiments.records import ExperimentPlayerRecord, ExperimentStep
from gptnt.experiments.suite.definition import Suite, SuiteIdentity, SuiteMatchup
from gptnt.experiments.suite.lock import MissionEntry, SuiteLock, SuiteLockEntry
from gptnt.players.actions import DoNothingAction
from gptnt.players.specification import PlayerCapabilities, PlayerProtocol

from tests._cli_runner import CliResult, invoke_cli
from tests._factories.experiments import make_experiment_spec, make_provenance, make_solved_bomb
from tests._factories.statics import write_statics_run

if TYPE_CHECKING:
    from gptnt.experiments.instance import PlayerContent

SUITE = "custom-submission-suite"
DEFUSER_STEP_INPUT_TOKENS = 100
EXPERT_STEP_INPUT_TOKENS = 7

_BASE_SPEC = make_experiment_spec()
_MISSIONS = tuple(make_experiment_spec(seed=seed).mission_spec for seed in (1, 2, 3))
_SUITE = Suite(
    name=SUITE,
    revision=7,
    modality=("language", "vision"),
    missions_path=Path("configs/missions/custom-submission"),
    defuser_protocol=_BASE_SPEC.defuser_protocol,
    expert_protocol=None,
    matchup=SuiteMatchup(pairing_type="no_expert"),
    manual_profile=_BASE_SPEC.manual_profile,
)
_SUITE_DIGEST = _SUITE.digest_for(_MISSIONS)
_SUITE_ENTRY = SuiteLockEntry(
    name=_SUITE.name,
    revision=_SUITE.revision,
    suite_digest=_SUITE_DIGEST,
    frozen_at="2026-08-20T00:00:00Z",
    gptnt_version="2.0.0",
    git_sha="a1b2c3d4",
    mission_keys=tuple(mission.mission_key for mission in _MISSIONS),
    config=_SUITE.model_dump(mode="json", exclude_none=True, exclude={"config_digest"}),
)
_SUITE_LOCK = SuiteLock.model_validate(
    {
        "suites": (_SUITE_ENTRY,),
        "missions": tuple(
            MissionEntry(mission_key=mission.mission_key, spec=mission) for mission in _MISSIONS
        ),
    }
)
_SUITE_IDENTITY = SuiteIdentity(
    suite_name=_SUITE.name, suite_revision=_SUITE.revision, suite_digest=_SUITE_DIGEST
)
_MISSIONS_BY_SEED = {mission.seed: mission for mission in _MISSIONS}


@pytest.fixture(autouse=True)
def local_suite_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every interactive build select the custom frozen suite used by its records."""
    lock_path = tmp_path / "source-suite.lock"
    _SUITE_LOCK.dump_to_path(lock_path)
    monkeypatch.setattr("gptnt.experiments.suite.lock.default_lock_path", lambda: lock_path)


def _fail_live_access(*_args: object, **_kwargs: object) -> None:
    pytest.fail("validation read live suite or mission configuration")


def _instance(*, seed: int, model: str, expert: str | None = None) -> ExperimentInstance:
    """An experiment instance for `model`, plus an optional expert."""
    spec = make_experiment_spec(seed=seed).model_copy(
        update={
            "mission_spec": _MISSIONS_BY_SEED[seed],
            "mission_set": _SUITE.mission_set,
            "suite_name": _SUITE_IDENTITY.suite_name,
            "suite_revision": _SUITE_IDENTITY.suite_revision,
            "suite_digest": _SUITE_IDENTITY.suite_digest,
            "defuser_name": model,
        }
    )
    expert_uuid = None
    expert_capabilities = None
    if expert is not None:
        spec = spec.model_copy(
            update={
                "defuser_protocol": spec.defuser_protocol.model_copy(
                    update={"is_playing_alone": False}
                ),
                "expert_name": expert,
                "expert_protocol": PlayerProtocol(
                    role="expert",
                    communication_style="sync",
                    is_playing_alone=False,
                    include_manual=True,
                ),
            }
        )
        expert_uuid = uuid4()
        expert_capabilities = PlayerCapabilities(player_name=expert, player_type="ai")
    return ExperimentInstance.model_validate(
        spec.model_dump()
        | {
            "session_id": uuid4(),
            "defuser_uuid": uuid4(),
            "expert_uuid": expert_uuid,
            "game_uuid": uuid4(),
            "defuser_capabilities": PlayerCapabilities(player_name=model, player_type="ai"),
            "expert_capabilities": expert_capabilities,
        }
    )


def _steps(instance: ExperimentInstance, player: PlayerContent) -> list[ExperimentStep]:
    """One player's record has steps.

    Only defuser steps contain a bomb state.
    """
    role = player.protocol.role
    is_defuser = role == "defuser"
    step = ExperimentStep(
        step=1,
        timestamp=1.0,
        role=role,
        session_id=instance.session_id,
        player_uuid=player.uuid,
        player_name=player.name,
        output=DoNothingAction(),
        raw_output="DoNothing",
        bomb_state=make_solved_bomb() if is_defuser else None,
        observation=None,
        usage=RunUsage(
            requests=1,
            input_tokens=DEFUSER_STEP_INPUT_TOKENS if is_defuser else EXPERT_STEP_INPUT_TOKENS,
            output_tokens=20,
        ),
        num_prompt_truncations=0,
    )
    return [step, step.model_copy(update={"step": 2, "timestamp": 2.0})]


def _write_record(
    outputs: Path, *, seed: int, model: str = "test-defuser", expert: str | None = None
) -> None:
    """Write one completed record per player of one experiment (they share the session id)."""
    instance = _instance(seed=seed, model=model, expert=expert)
    players = [instance.defuser]
    if instance.expert is not None:
        players.append(instance.expert)
    for player in players:
        record = ExperimentPlayerRecord(
            experiment_instance=instance,
            player_content=player,
            step_records=_steps(instance, player),
            is_hard_crash=False,
            **make_provenance().model_dump(),
        )
        write_player_record_parquet(
            blobbed_steps=[blob_step(each) for each in record.step_records],
            footer=footer_from_player_record(record),
            output_path=outputs / f"experiment-{uuid4()}.parquet",
        )


def _build_db(tmp_path: Path, records: list[tuple[int, str]]) -> Path:
    """Write recorder parquet for each (seed, model) and ingest it into a fresh DuckDB."""
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    for seed, model in records:
        _write_record(outputs, seed=seed, model=model)
    db_path = tmp_path / "experiments.duckdb"
    ingest_player_records(
        player_record_paths=sorted(outputs.glob("*.parquet")), db_path=db_path, max_workers=2
    )
    return db_path


def _run_new(db_path: Path, output_path: Path, *extra: str) -> None:
    """Invoke `submission new` for one suite and assert it exits cleanly."""
    result = invoke_cli(
        build_app(),
        [
            "submission",
            "new",
            str(db_path),
            "--suite",
            SUITE,
            "--output-dir",
            str(output_path),
            *extra,
        ],
    )
    assert result.exit_code == 0, result.output


def _read_manifest(bundle_dir: Path) -> dict[str, Any]:
    """Load a bundle's `submission.yaml`."""
    return yaml.safe_load((bundle_dir / "submission.yaml").read_text())


def test_new_builds_a_self_contained_bundle_that_validates_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = _build_db(tmp_path, [(1, "test-defuser"), (2, "test-defuser"), (3, "test-defuser")])

    _run_new(db_path, tmp_path / "submissions")
    bundle_dir = next((tmp_path / "submissions").rglob("submission.yaml")).parent

    rows = read_typed_parquet(SubmissionExperiment, bundle_dir / "experiments.parquet")
    assert len(rows) == 3
    assert all(row.final_bomb_state.is_solved for row in rows)
    assert all(row.defuser_usage.input_tokens == DEFUSER_STEP_INPUT_TOKENS * 2 for row in rows)
    assert all(row.expert_usage is None for row in rows)  # solo play: no expert steps

    manifest = _read_manifest(bundle_dir)
    assert "system" not in manifest  # the model(s) live in the role-tagged players list
    # players is a role-tagged list; the defuser is first, carrying its PlayerIdentity.
    assert [entry["role"] for entry in manifest["players"]] == ["defuser"]  # solo play
    defuser = manifest["players"][0]
    assert defuser["capabilities"]["player_name"] == "test-defuser"
    assert defuser["fingerprint"]  # stamped at the submission boundary
    assert defuser["identity"]["organisation"] == "GPTNT"  # configs/player/test-defuser.yaml
    assert manifest["measured"]["suite_name"] == SUITE
    assert manifest["submitter"] == {"name": "", "contact": "", "affiliation": None}

    snapshot = SuiteLock.from_lock_path(bundle_dir / "suite.lock")
    assert snapshot.suites == (_SUITE_ENTRY,)
    assert set(snapshot.mission_specs()) == set(_SUITE_ENTRY.mission_keys)

    manifest["submitter"] = {"name": "Ada Lovelace", "contact": "@ada", "affiliation": None}
    _ = (bundle_dir / "submission.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False))

    monkeypatch.setattr("gptnt.experiments.suite.lock.default_lock_path", _fail_live_access)
    monkeypatch.setattr("gptnt.experiments.suite.compose.compose_suite", _fail_live_access)
    monkeypatch.setattr("gptnt.experiments.suite.definition.load_missions", _fail_live_access)
    result = invoke_cli(build_app(), ["submission", "validate", str(bundle_dir)])
    assert result.exit_code == 0, result.output


def test_two_player_usage_is_split_per_role(tmp_path: Path) -> None:
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    _write_record(outputs, seed=1, expert="test-expert")
    db_path = tmp_path / "experiments.duckdb"
    ingest_player_records(
        player_record_paths=sorted(outputs.glob("*.parquet")), db_path=db_path, max_workers=2
    )

    _run_new(db_path, tmp_path / "submissions")
    bundle_dir = next((tmp_path / "submissions").rglob("submission.yaml")).parent

    row = read_typed_parquet(SubmissionExperiment, bundle_dir / "experiments.parquet")[0]
    # each player's steps are summed separately, not lumped into one session total
    assert row.defuser_usage.input_tokens == DEFUSER_STEP_INPUT_TOKENS * 2
    assert row.expert_usage is not None
    assert row.expert_usage.input_tokens == EXPERT_STEP_INPUT_TOKENS * 2

    manifest = _read_manifest(bundle_dir)
    assert [entry["role"] for entry in manifest["players"]] == ["defuser", "expert"]
    assert manifest["players"][1]["capabilities"]["player_name"] == "test-expert"


def test_rebuild_preserves_hand_filled_fields(tmp_path: Path) -> None:
    db_path = _build_db(tmp_path, [(1, "test-defuser")])
    output_path = tmp_path / "submissions"

    _run_new(db_path, output_path)
    bundle_dir = next(output_path.rglob("submission.yaml")).parent
    manifest = _read_manifest(bundle_dir)
    manifest["submitter"]["name"] = "Ada Lovelace"
    manifest["submitter"]["contact"] = "@ada"
    _ = (bundle_dir / "submission.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False))

    _run_new(db_path, output_path)  # rebuild

    rebuilt = _read_manifest(bundle_dir)
    assert rebuilt["submitter"]["name"] == "Ada Lovelace"  # hand edits survive
    assert rebuilt["submitter"]["contact"] == "@ada"
    # derived field still correct
    assert rebuilt["players"][0]["capabilities"]["player_name"] == "test-defuser"


def test_model_filter_selects_one_model(tmp_path: Path) -> None:
    # Both models need an `identity` in configs/player/ (a submission must be attributable).
    db_path = _build_db(tmp_path, [(1, "test-defuser"), (2, "test-expert")])

    _run_new(db_path, tmp_path / "submissions", "--model", "test-expert")

    # each bundle is one flat dir: <into>/YYYYMMDD_<display-slug>_<capfp8>_<suite>_<ver>/
    folders = {path.parent.name for path in (tmp_path / "submissions").rglob("submission.yaml")}
    bundles = {
        _read_manifest(path.parent)["players"][0]["capabilities"]["player_name"]
        for path in (tmp_path / "submissions").rglob("submission.yaml")
    }
    assert bundles == {"test-expert"}
    assert not any("test-defuser" in name for name in folders)


def _run_statics_new(root: Path, into: Path, *extra: str) -> CliResult:
    """Invoke `submission new` for a statics-only build against `root`."""
    return invoke_cli(
        build_app(),
        [
            "submission",
            "new",
            "--empty-suite",  # statics-only: don't inherit the default leaderboard suites
            "--statics-output-dir",
            str(root),
            "--static",
            "expert-ocr",
            "--output-dir",
            str(into),
            *extra,
        ],
    )


def test_statics_bundle_from_filesystem(tmp_path: Path) -> None:
    root = tmp_path / "statics"
    _ = write_statics_run(root)
    into = tmp_path / "submissions"

    result = _run_statics_new(root, into)
    assert result.exit_code == 0, result.output

    bundle_dir = next(into.rglob("submission.yaml")).parent
    # Aggregated metrics live in a separate metrics.json, not in the manifest.
    assert orjson.loads((bundle_dir / "metrics.json").read_bytes()) == {"module": {"total": 0.87}}
    assert not (bundle_dir / "predictions.parquet").exists()
    manifest = _read_manifest(bundle_dir)
    defuser = manifest["players"][0]
    assert defuser["role"] == "defuser"
    assert defuser["capabilities"]["player_name"] == "gpt-5-2"
    assert manifest["measured"]["task_name"] == "expert-ocr"
    assert manifest["measured"]["hf_repo_id"] == "GPTNT/expert-element-ocr"
    assert "metrics" not in manifest
    assert manifest["submitter"] == {"name": "", "contact": "", "affiliation": None}


def test_statics_model_filter_matches_player_name_not_dir(tmp_path: Path) -> None:
    """`--model` filters on the run's `player_name`, even when the run dir is the model string."""
    root = tmp_path / "statics"
    # The run dir is the resolved model string. The leaderboard player_name differs.
    _ = write_statics_run(root, model_dir="gpt-5-mini-2026", player_name="gpt-5-2")
    into = tmp_path / "submissions"

    result = _run_statics_new(root, into, "--model", "gpt-5-2")
    assert result.exit_code == 0, result.output

    bundle_dir = next(into.rglob("submission.yaml")).parent
    assert _read_manifest(bundle_dir)["players"][0]["capabilities"]["player_name"] == "gpt-5-2"


def test_statics_unparsable_run_meta_is_skipped_not_fatal(tmp_path: Path) -> None:
    """A broken run_meta.json is skipped with a warning.

    A valid sibling run still builds.
    """
    root = tmp_path / "statics"
    _ = write_statics_run(root, model_dir="good", player_name="gpt-5-2")
    broken = root / "expert-ocr_predictions" / "broken"
    broken.mkdir(parents=True)
    _ = (broken / "run_meta.json").write_text("{ not valid json")
    _ = (broken / "metrics.json").write_bytes(orjson.dumps({"module": {"total": 0.1}}))
    into = tmp_path / "submissions"

    result = _run_statics_new(root, into)
    assert result.exit_code == 0, result.output
    # Only the good run produced a bundle. The broken run was skipped.
    bundles = list(into.rglob("submission.yaml"))
    assert len(bundles) == 1
    manifest = _read_manifest(bundles[0].parent)
    assert manifest["players"][0]["capabilities"]["player_name"] == "gpt-5-2"
