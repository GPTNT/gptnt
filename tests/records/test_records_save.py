import json
from pathlib import Path
from uuid import uuid4

import duckdb
import pytest
from pydantic_ai import BinaryContent, ModelMessage, ModelRequest, ModelResponse, TextPart
from pydantic_ai.messages import SystemPromptPart, UserPromptPart
from pydantic_ai.result import RunUsage
from pytest_cases import fixture
from whenever import Instant

from gptnt.experiments.db.extract import extract_metadata_from_paths
from gptnt.experiments.db.ingest import ingest_player_records
from gptnt.experiments.db.read import load_experiment_summaries
from gptnt.experiments.instance import ExperimentInstance, PlayerContent
from gptnt.experiments.recorder.local import ExperimentPlayerRecorder
from gptnt.experiments.recorder.parquet import (
    FORMAT_VERSION,
    KEY_FOOTER,
    KEY_FORMAT_VERSION,
    blob_step,
    footer_from_player_record,
    load_player_record_from_parquet,
    read_record_footer,
    write_player_record_parquet,
)
from gptnt.experiments.records import ExperimentPlayerRecord, ExperimentStep, ExperimentSummary
from gptnt.experiments.spec import ExperimentSpec
from gptnt.ktane.mission_spec import KtaneMissionSpec
from gptnt.ktane.state.bomb import BombState
from gptnt.players.actions import DoNothingAction
from gptnt.players.observation_handler import Observation
from gptnt.players.result import AgentCallResult
from gptnt.players.specification import PlayerCapabilities, PlayerProtocol

from tests._factories.experiments import (
    make_experiment_instance,
    make_experiment_spec,
    make_manual_profile,
    make_provenance,
)

_MISMATCHED_PROTECTED_CONTENT_DIGEST = f"sha256:{'2' * 64}"


@fixture
def tiny_image_bytes() -> bytes:
    """Create a tiny 2x2 black PNG image as bytes."""
    return (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x02\x00\x00\x00\x02\x08\x02\x00\x00\x00\xfd\xd4\x9as"
        b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x00\x00\x00\x00IEND\xaeB`\x82"
    )


@fixture
def observation(tiny_image_bytes: bytes) -> Observation:
    """Create a minimal observation with tiny placeholder images."""
    return Observation(
        frames=[tiny_image_bytes, tiny_image_bytes],
        segm_mask=tiny_image_bytes,
        som_image=tiny_image_bytes,
    )


@fixture
def simple_model_messages(tiny_image_bytes: bytes) -> list[ModelMessage]:
    """Create simple model messages for testing."""
    return [
        ModelRequest(
            parts=[
                SystemPromptPart(content="You are a helpful assistant."),
                UserPromptPart(
                    content=[
                        TextPart(content="What is 2+2?"),
                        BinaryContent(data=tiny_image_bytes, media_type="image/png"),
                    ],
                    timestamp=Instant.now().py_datetime(),
                ),
            ]
        ),
        ModelResponse(
            parts=[TextPart(content="The answer is 4.")], timestamp=Instant.now().py_datetime()
        ),
    ]


@fixture
def bomb_state() -> BombState:
    """Create a minimal bomb state for testing."""
    return BombState.model_validate(
        {
            "seed": 12345,
            "maxStrikes": 3,
            "strikes": None,
            "isDetonated": False,
            "isSolved": False,
            "isLightOn": True,
            "bombSide": "front",
            "timerModule": {
                "name": "Timer",
                "onFront": True,
                "index": 0,
                "seconds_remaining": 300.0,
            },
            "widgets": [],
            "modules": [],
        }
    )


@fixture
def player_content() -> PlayerContent:
    """Create a minimal player content."""
    return PlayerContent(
        protocol=PlayerProtocol(
            role="defuser", communication_style="sync", is_playing_alone=True, include_manual=False
        ),
        name="test-player",
        uuid=uuid4(),
        capabilities=PlayerCapabilities(player_name="test-defuser", player_type="ai"),
    )


@fixture
def experiment_instance() -> ExperimentInstance:
    """Create a minimal experiment instance."""
    mission_spec = KtaneMissionSpec(
        seed=12345,
        time_limit=300,
        num_strikes_allowed=3,
        components=["Wires", "CommunityModule"],
        optional_widgets=1,
        needy_time=60,
    )
    experiment_spec = ExperimentSpec(
        mission_spec=mission_spec,
        mission_set="single_module",
        suite_name="test-suite",
        suite_revision=1,
        suite_digest="0" * 32,
        manual_profile=make_manual_profile(),
        defuser_protocol=PlayerProtocol(
            role="defuser", communication_style="sync", is_playing_alone=True, include_manual=False
        ),
        defuser_name="test-defuser",
        expert_protocol=None,
        expert_name=None,
    )

    return ExperimentInstance.model_validate(
        experiment_spec.model_dump()
        | {
            "session_id": uuid4(),
            "defuser_uuid": uuid4(),
            "expert_uuid": None,
            "game_uuid": uuid4(),
            "start_time": Instant.now(),
            "defuser_capabilities": PlayerCapabilities(
                player_name="test-defuser", player_type="ai"
            ),
            "expert_capabilities": None,
        }
    )


@fixture
def step_record(
    experiment_instance: ExperimentInstance,
    player_content: PlayerContent,
    simple_model_messages: list[ModelMessage],
    bomb_state: BombState,
    observation: Observation,
) -> ExperimentStep:
    """Create a minimal step record with inline observation."""
    return ExperimentStep(
        step=1,
        timestamp=1.0,
        role="defuser",
        session_id=experiment_instance.session_id,
        player_uuid=player_content.uuid,
        player_name=player_content.name,
        output=DoNothingAction(),
        raw_output="DoNothing",
        thoughts="Testing step record",
        input_messages=simple_model_messages,
        new_messages=simple_model_messages,
        bomb_state=bomb_state,
        observation=observation,
        usage=RunUsage(requests=1, input_tokens=100, output_tokens=20),
        num_prompt_truncations=0,
        error_type=None,
        is_reflection=False,
    )


def _build_player_record(
    instance: ExperimentInstance, content: PlayerContent, step: ExperimentStep
) -> ExperimentPlayerRecord:
    # The recorder stamps every step with the player's own uuid; mirror that so the footer's
    # player_uuid matches the step rows (the basis for ingest idempotency).
    step1 = step.model_copy(
        update={
            "role": content.protocol.role,
            "session_id": instance.session_id,
            "player_uuid": content.uuid,
            "player_name": content.name,
        }
    )
    step2 = step1.model_copy(update={"step": 2, "timestamp": 2.0, "thoughts": "Second step"})
    return ExperimentPlayerRecord(
        experiment_instance=instance,
        player_content=content,
        step_records=[step1, step2],
        is_hard_crash=False,
        **make_provenance().model_dump(),
    )


@pytest.mark.anyio
async def test_recorder_saves_parquet_roundtrips(
    tmp_path: Path,
    experiment_instance: ExperimentInstance,
    player_content: PlayerContent,
    step_record: ExperimentStep,
) -> None:
    """The real recorder method writes a parquet file that round-trips back to the same record."""
    player_record = _build_player_record(experiment_instance, player_content, step_record)

    recorder = ExperimentPlayerRecorder(
        capabilities=PlayerCapabilities(player_name="test-defuser", player_type="ai")
    )
    recorder.output_dir = tmp_path
    await recorder.save_player_record_to_disk(player_record=player_record)

    output_path = (
        tmp_path / f"experiment-{experiment_instance.attempt_name}-{player_content.uuid}.parquet"
    )
    assert output_path.exists()

    loaded = load_player_record_from_parquet(output_path)
    assert len(loaded.step_records) == 2
    assert loaded.num_steps == 2
    assert [step.step for step in loaded.step_records] == [1, 2]

    first = loaded.step_records[0]
    assert isinstance(first.output, DoNothingAction)
    assert isinstance(first.observation, Observation)
    assert isinstance(step_record.observation, Observation)
    assert first.observation.frames == step_record.observation.frames
    assert first.usage.input_tokens == step_record.usage.input_tokens
    assert first.bomb_state is not None
    assert len(first.input_messages) == len(step_record.input_messages)

    # Footer outcome + provenance survive the trip.
    footer = read_record_footer(output_path)
    assert footer.final_bomb_state is not None
    assert footer.is_hard_crash is False
    assert loaded.gptnt_version == player_record.gptnt_version
    assert loaded.release_commit == player_record.release_commit
    assert (
        loaded.release_protected_content_digest == player_record.release_protected_content_digest
    )
    assert loaded.protected_content_digest == player_record.protected_content_digest
    assert (
        footer.release_protected_content_digest == player_record.release_protected_content_digest
    )
    assert footer.protected_content_digest == player_record.protected_content_digest


def test_legacy_format_three_footer_without_digests_remains_readable(
    tmp_path: Path,
    experiment_instance: ExperimentInstance,
    player_content: PlayerContent,
    step_record: ExperimentStep,
) -> None:
    record = _build_player_record(experiment_instance, player_content, step_record)
    footer = footer_from_player_record(record)
    footer_data = json.loads(footer[KEY_FOOTER])
    footer_data.pop("release_protected_content_digest", None)
    footer_data.pop("protected_content_digest", None)
    footer[KEY_FOOTER] = json.dumps(footer_data).encode()
    path = tmp_path / "legacy.parquet"
    write_player_record_parquet(
        blobbed_steps=[blob_step(step) for step in record.step_records],
        footer=footer,
        output_path=path,
    )

    loaded = read_record_footer(path)

    assert footer[KEY_FORMAT_VERSION] == FORMAT_VERSION == b"3"
    assert loaded.release_protected_content_digest is None
    assert loaded.protected_content_digest is None


def test_record_footer_rejects_v1_format_version(
    tmp_path: Path,
    experiment_instance: ExperimentInstance,
    player_content: PlayerContent,
    step_record: ExperimentStep,
) -> None:
    """A format-2 footer directs the caller to v1 tooling instead of inferring missing fields."""
    record = _build_player_record(experiment_instance, player_content, step_record)
    footer = footer_from_player_record(record)
    footer[KEY_FORMAT_VERSION] = b"2"

    path = tmp_path / "bad-version.parquet"
    write_player_record_parquet(
        blobbed_steps=[blob_step(step) for step in record.step_records],
        footer=footer,
        output_path=path,
    )

    with pytest.raises(
        ValueError, match="format_version 2 is a v1 artifact and requires v1 tooling"
    ):
        _ = read_record_footer(path)


@pytest.mark.anyio
async def test_recorder_skips_empty_record(
    tmp_path: Path, experiment_instance: ExperimentInstance, player_content: PlayerContent
) -> None:
    """A record with no steps writes nothing (no empty parquet file)."""
    empty_record = ExperimentPlayerRecord(
        experiment_instance=experiment_instance,
        player_content=player_content,
        step_records=[],
        is_hard_crash=False,
        **make_provenance().model_dump(),
    )
    recorder = ExperimentPlayerRecorder(
        capabilities=PlayerCapabilities(player_name="test-defuser", player_type="ai")
    )
    recorder.output_dir = tmp_path
    await recorder.save_player_record_to_disk(player_record=empty_record)

    # This test assertion uses a synchronous glob. It is not a hot path.
    assert list(tmp_path.glob("*.parquet")) == []  # noqa: ASYNC240


@pytest.mark.anyio
async def test_recorder_uses_shared_origin_and_supplied_dispatch_timestamp(
    experiment_instance: ExperimentInstance,
    player_content: PlayerContent,
    simple_model_messages: list[ModelMessage],
) -> None:
    provenance = make_provenance()
    first = ExperimentPlayerRecorder(capabilities=player_content.capabilities)
    second = ExperimentPlayerRecorder(capabilities=player_content.capabilities)

    for recorder in (first, second):
        await recorder.configure_for_experiment(
            experiment_instance=experiment_instance,
            protocol=player_content.protocol,
            player_uuid=player_content.uuid,
            provenance=provenance,
        )

    assert first.start_time == second.start_time == experiment_instance.start_time

    first.track_step(
        event_time=experiment_instance.start_time.add(seconds=2.75),
        agent_call_result=AgentCallResult(
            output=DoNothingAction(), thoughts=None, usage=RunUsage(), new_messages=[]
        ),
        num_prompt_truncations=0,
        input_messages=simple_model_messages,
    )

    assert first.step_records[0].timestamp == pytest.approx(2.75)


@pytest.mark.anyio
async def test_recorder_reuses_the_experiment_provenance_snapshot(
    experiment_instance: ExperimentInstance, player_content: PlayerContent
) -> None:
    """Repeated record builds use the snapshot supplied by the experiment boundary."""
    provenance = make_provenance()
    recorder = ExperimentPlayerRecorder(capabilities=player_content.capabilities)

    # Configuration binds the experiment-wide snapshot to this player's output representations.
    await recorder.configure_for_experiment(
        experiment_instance=experiment_instance,
        protocol=player_content.protocol,
        player_uuid=player_content.uuid,
        provenance=provenance,
    )
    player_record = recorder.build_player_record()
    second_record = recorder.build_player_record()

    assert player_record.release_tag == provenance.release_tag
    assert second_record.protected_content_modified is provenance.protected_content_modified

    # Reset clears the earlier snapshot before the recorder accepts another experiment.
    recorder.reset()
    next_provenance = provenance.model_copy(
        update={
            "protected_content_digest": _MISMATCHED_PROTECTED_CONTENT_DIGEST,
            "protected_content_modified": True,
        }
    )
    await recorder.configure_for_experiment(
        experiment_instance=experiment_instance,
        protocol=player_content.protocol,
        player_uuid=player_content.uuid,
        provenance=next_provenance,
    )
    assert recorder.build_player_record().protected_content_modified is True


def _two_player_instance() -> ExperimentInstance:
    spec = make_experiment_spec().model_copy(
        update={
            "suite_name": "storage-contract",
            "suite_revision": 7,
            "suite_digest": "7" * 32,
            "defuser_protocol": PlayerProtocol(
                role="defuser",
                communication_style="sync",
                is_playing_alone=False,
                include_manual=False,
            ),
            "expert_protocol": PlayerProtocol(
                role="expert",
                communication_style="sync",
                is_playing_alone=False,
                include_manual=True,
            ),
            "expert_name": "test-expert",
        }
    )
    return make_experiment_instance(spec)


def test_grouped_player_files_report_every_identity_disagreement(
    tmp_path: Path, step_record: ExperimentStep
) -> None:
    """Aggregation reports all identity conflicts instead of selecting one player's footer."""
    instance = _two_player_instance()
    first_record = _build_player_record(instance, instance.defuser, step_record)
    peer_instance = instance.model_copy(
        update={"suite_revision": 8, "suite_digest": "f" * 32, "defuser_uuid": uuid4()}
    )
    peer_expert = peer_instance.expert
    assert peer_expert is not None
    second_record = _build_player_record(
        peer_instance, peer_expert, step_record.model_copy(update={"bomb_state": None})
    ).model_copy(
        update={
            "release_commit": "different-commit",
            "protected_content_digest": _MISMATCHED_PROTECTED_CONTENT_DIGEST,
            "protected_content_modified": True,
        }
    )

    # Write two player files for the same session with different captured benchmark states.
    first_path = tmp_path / "defuser.parquet"
    second_path = tmp_path / "expert.parquet"
    _write_record_parquet(first_record, first_path)
    _write_record_parquet(second_record, second_path)

    with pytest.raises(
        ValueError,
        match=(
            "Grouped experiment files disagree on summary identity: release_commit, "
            "protected_content_digest, protected_content_modified, suite_revision, suite_digest, "
            "defuser_uuid, ExperimentSpec fingerprint"
        ),
    ):
        _ = extract_metadata_from_paths([first_path, second_path])


def _write_record_parquet(record: ExperimentPlayerRecord, path: Path) -> None:
    write_player_record_parquet(
        blobbed_steps=[blob_step(step) for step in record.step_records],
        footer=footer_from_player_record(record),
        output_path=path,
    )


def _write_legacy_record_parquet(record: ExperimentPlayerRecord, path: Path) -> None:
    footer = footer_from_player_record(record)
    footer_data = json.loads(footer[KEY_FOOTER])
    footer_data.pop("release_protected_content_digest")
    footer_data.pop("protected_content_digest")
    footer[KEY_FOOTER] = json.dumps(footer_data).encode()
    write_player_record_parquet(
        blobbed_steps=[blob_step(step) for step in record.step_records],
        footer=footer,
        output_path=path,
    )


def test_ingest_recorder_parquet_into_duckdb(tmp_path: Path, step_record: ExperimentStep) -> None:
    """Player footers reconstruct a summary with the complete recorded identity."""
    instance = _two_player_instance()
    provenance = make_provenance()
    defuser_record = _build_player_record(instance, instance.defuser, step_record)
    expert = instance.expert
    assert expert is not None
    expert_record = _build_player_record(
        instance, expert, step_record.model_copy(update={"bomb_state": None})
    )
    defuser_path = tmp_path / f"experiment-{instance.attempt_name}-{instance.defuser.uuid}.parquet"
    expert_path = tmp_path / f"experiment-{instance.attempt_name}-{expert.uuid}.parquet"
    _write_record_parquet(defuser_record, defuser_path)
    _write_record_parquet(expert_record, expert_path)

    db_path = tmp_path / "test.duckdb"
    ingest_kwargs = {
        "player_record_paths": [defuser_path, expert_path],
        "db_path": db_path,
        "max_workers": 1,
    }
    ingest_player_records(**ingest_kwargs)

    with duckdb.connect(db_path) as con:
        step_count = con.execute("SELECT COUNT(*) FROM experiment_step").fetchone()

    assert step_count is not None
    assert step_count[0] == 4
    final_bomb_state = defuser_record.final_bomb_state
    assert final_bomb_state is not None
    assert load_experiment_summaries(db_path) == [
        ExperimentSummary.from_instance_and_bomb_state(
            instance=instance,
            final_bomb_state=final_bomb_state,
            is_hard_crash=False,
            provenance=provenance,
        )
    ]

    # Idempotent: a second ingest of both player files adds nothing.
    ingest_player_records(**ingest_kwargs)
    with duckdb.connect(db_path) as con:
        again = con.execute("SELECT COUNT(*) FROM experiment_step").fetchone()
    assert again is not None
    assert again[0] == 4


def test_ingest_preserves_current_and_in_flight_legacy_provenance(
    tmp_path: Path, step_record: ExperimentStep
) -> None:
    current_instance = make_experiment_instance(make_experiment_spec(seed=101))
    legacy_instance = make_experiment_instance(make_experiment_spec(seed=202))
    current_record = _build_player_record(current_instance, current_instance.defuser, step_record)
    legacy_record = _build_player_record(legacy_instance, legacy_instance.defuser, step_record)
    current_path = tmp_path / "current.parquet"
    legacy_path = tmp_path / "legacy.parquet"
    _write_record_parquet(current_record, current_path)
    _write_legacy_record_parquet(legacy_record, legacy_path)

    db_path = tmp_path / "mixed.duckdb"
    ingest_player_records(
        player_record_paths=[legacy_path, current_path], db_path=db_path, max_workers=1
    )

    with duckdb.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT seed, release_protected_content_digest, protected_content_digest "
            "FROM experiment_summary ORDER BY seed"
        ).fetchall()

    digest = make_provenance().protected_content_digest
    assert rows == [(101, digest, digest), (202, None, None)]
