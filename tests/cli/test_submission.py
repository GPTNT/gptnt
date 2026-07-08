"""End-to-end tests for `gptnt submission new`, driven off a real DuckDB built by the ingest path.

Records are written as recorder parquet, ingested into a temp `experiments.duckdb`, and the bundle
is built through the CLI. The human-only fields (submitter + declared system attribution) must be
blank on build and preserved across a rebuild.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import yaml
from pydantic_ai import RunUsage

from gptnt.cli.__main__ import build_app
from gptnt.cli.submission._bundle import read_experiments_payload
from gptnt.experiments.db.ingest import ingest_player_records
from gptnt.experiments.descriptor import ExperimentDescriptor
from gptnt.experiments.models import ExperimentPlayerRecord, ExperimentStep
from gptnt.experiments.recorder.parquet import (
    blob_step,
    footer_from_player_record,
    write_player_record_parquet,
)
from gptnt.ktane.state.bomb import BombState
from gptnt.players.actions import DoNothingAction
from gptnt.players.specification import PlayerCapabilities, PlayerProtocol

from tests._cli_runner import invoke_cli
from tests._factories.experiments import make_experiment_spec

if TYPE_CHECKING:
    from pathlib import Path

    from gptnt.experiments.descriptor import PlayerContent

SUITE = "single-parametric-sync"
DEFUSER_STEP_INPUT_TOKENS = 100
EXPERT_STEP_INPUT_TOKENS = 7


def _solved_bomb() -> BombState:
    """A solved bomb (empty modules; the is-solved validator marks an empty bomb solved)."""
    return BombState.model_validate(
        {
            "seed": 1,
            "maxStrikes": 3,
            "strikes": None,
            "isDetonated": False,
            "isSolved": True,
            "isLightOn": True,
            "bombSide": "front",
            "timerModule": {
                "name": "Timer",
                "onFront": True,
                "index": 0,
                "secondsRemaining": 100.0,
            },
            "widgets": [],
            "modules": [],
        }
    )


def _descriptor(*, seed: int, model: str, expert: str | None = None) -> ExperimentDescriptor:
    """A descriptor for `model` (defuser_name and player_name kept identical), plus any expert."""
    spec = make_experiment_spec(seed=seed).model_copy(update={"defuser_name": model})
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
                    receive_feedback_after_action=False,
                    allow_magic_actions=False,
                ),
            }
        )
        expert_uuid = uuid4()
        expert_capabilities = PlayerCapabilities(player_name=expert, player_type="ai")
    return ExperimentDescriptor(
        experiment_spec=spec,
        session_id=uuid4(),
        defuser_uuid=uuid4(),
        expert_uuid=expert_uuid,
        game_uuid=uuid4(),
        defuser_capabilities=PlayerCapabilities(player_name=model, player_type="ai"),
        expert_capabilities=expert_capabilities,
    )


def _steps(descriptor: ExperimentDescriptor, player: PlayerContent) -> list[ExperimentStep]:
    """Two steps for one player's record; only the defuser's steps carry a bomb state."""
    role = player.protocol.role
    is_defuser = role == "defuser"
    step = ExperimentStep(
        step=1,
        timestamp=1.0,
        role=role,
        session_id=descriptor.session_id,
        player_uuid=player.uuid,
        player_name=player.name,
        output=DoNothingAction(),
        raw_output="DoNothing",
        bomb_state=_solved_bomb() if is_defuser else None,
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
    descriptor = _descriptor(seed=seed, model=model, expert=expert)
    players = [descriptor.defuser]
    if descriptor.expert is not None:
        players.append(descriptor.expert)
    for player in players:
        record = ExperimentPlayerRecord(
            experiment_descriptor=descriptor,
            player_content=player,
            step_records=_steps(descriptor, player),
            is_hard_crash=False,
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


def test_new_writes_a_bundle_with_blank_human_fields(tmp_path: Path) -> None:
    db_path = _build_db(tmp_path, [(1, "test-defuser"), (2, "test-defuser"), (3, "test-defuser")])

    _run_new(db_path, tmp_path / "submissions")
    bundle_dir = next((tmp_path / "submissions").rglob("submission.yaml")).parent

    rows = read_experiments_payload(bundle_dir / "experiments.parquet")
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

    row = read_experiments_payload(bundle_dir / "experiments.parquet")[0]
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

    # the model dir is the grandparent of submission.yaml: <into>/<model>_<capfp8>/<suite>@<rev>/
    models = {
        path.parent.parent.name for path in (tmp_path / "submissions").rglob("submission.yaml")
    }
    bundles = {
        _read_manifest(path.parent)["players"][0]["capabilities"]["player_name"]
        for path in (tmp_path / "submissions").rglob("submission.yaml")
    }
    assert bundles == {"test-expert"}
    assert not any(name.startswith("test-defuser") for name in models)


def _write_statics_outputs(root: Path) -> None:
    """A statics outputs dir with aggregated metrics and a stamped run_meta.json."""
    out = root / "expert-ocr_predictions" / "gpt-5-2"
    out.mkdir(parents=True)
    # player_name matches configs/player/gpt-5-2.yaml so its PlayerIdentity resolves.
    capabilities = PlayerCapabilities(player_name="gpt-5-2", player_type="ai")
    _ = (out / "run_meta.json").write_text(
        json.dumps(
            {
                "model_name": "gpt-5-2",
                "run_date": "2026-07-02T10:00:00Z",
                "statics": {
                    "task_name": "expert-ocr",
                    "hf_repo_id": "GPTNT/expert-element-ocr",
                    "dataset_split": None,
                    "requested_revision": "v1",
                    "resolved_revision": "a1b2c3d4e5f6",
                },
                "capabilities": capabilities.model_dump(mode="json"),
                "provenance": {"gptnt_version": "0.15.0", "git_sha": "a1b2c3d4"},
            }
        )
    )
    _ = (out / "metrics.json").write_text(json.dumps({"module": {"total": 0.87}}))


def test_statics_bundle_from_filesystem(tmp_path: Path) -> None:
    root = tmp_path / "statics"
    _write_statics_outputs(root)
    into = tmp_path / "submissions"

    result = invoke_cli(
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
        ],
    )
    assert result.exit_code == 0, result.output

    bundle_dir = next(into.rglob("submission.yaml")).parent
    # Aggregated metrics live in a separate metrics.json, not in the manifest.
    assert json.loads((bundle_dir / "metrics.json").read_text()) == {"module": {"total": 0.87}}
    assert not (bundle_dir / "predictions.parquet").exists()
    manifest = _read_manifest(bundle_dir)
    defuser = manifest["players"][0]
    assert defuser["role"] == "defuser"
    assert defuser["capabilities"]["player_name"] == "gpt-5-2"
    assert manifest["measured"]["task_name"] == "expert-ocr"
    assert manifest["measured"]["hf_repo_id"] == "GPTNT/expert-element-ocr"
    assert "metrics" not in manifest
    assert manifest["submitter"] == {"name": "", "contact": "", "affiliation": None}
