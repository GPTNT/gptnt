from pathlib import Path
from uuid import uuid4

import duckdb
import orjson
import pytest
from pydantic_ai import BinaryContent, ModelMessage, ModelRequest, ModelResponse, TextPart
from pydantic_ai.messages import SystemPromptPart, UserPromptPart
from pydantic_ai.result import RunUsage
from pytest_cases import fixture
from whenever import Instant

from gptnt.experiments.db.ingest import ingest_player_records
from gptnt.experiments.descriptor import ExperimentDescriptor, PlayerContent
from gptnt.experiments.duckdb import arrow_schema_for, generate_duckdb_schema
from gptnt.experiments.models import ExperimentPlayerRecord, ExperimentStep, ExperimentSummary
from gptnt.experiments.recorder.local import ExperimentPlayerRecorder
from gptnt.experiments.recorder.parquet import (
    KEY_FORMAT_VERSION,
    blob_step,
    footer_from_player_record,
    load_player_record_from_parquet,
    read_record_footer,
    write_player_record_parquet,
)
from gptnt.experiments.spec import ExperimentSpec
from gptnt.ktane.mission_spec import KtaneMissionSpec
from gptnt.ktane.state.bomb import BombState
from gptnt.players.actions import DoNothingAction
from gptnt.players.observation_handler import Observation
from gptnt.specification import PlayerCapabilities, PlayerProtocol


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
def player_protocol() -> PlayerProtocol:
    """Create a minimal player protocol."""
    return PlayerProtocol(
        role="defuser",
        communication_style="sync",
        is_playing_alone=True,
        include_manual=False,
        receive_feedback_after_action=False,
        allow_magic_actions=False,
    )


@fixture
def player_content(player_protocol: PlayerProtocol) -> PlayerContent:
    """Create a minimal player content."""
    return PlayerContent(
        protocol=player_protocol,
        name="test-player",
        uuid=uuid4(),
        capabilities=PlayerCapabilities(player_name="test-defuser", player_type="ai"),
    )


@fixture
def experiment_descriptor(player_protocol: PlayerProtocol) -> ExperimentDescriptor:
    """Create a minimal experiment descriptor."""
    mission_spec = KtaneMissionSpec(
        seed=12345,
        time_limit=300,
        num_strikes_allowed=3,
        components=["Wires"],
        optional_widgets=1,
        needy_time=60,
    )
    experiment_spec = ExperimentSpec(
        mission_spec=mission_spec,
        mission_set="single_module",
        suite_name="test-suite",
        suite_revision=1,
        defuser_protocol=player_protocol,
        defuser_name="test-defuser",
        expert_protocol=None,
        expert_name=None,
    )

    return ExperimentDescriptor(
        experiment_spec=experiment_spec,
        session_id=uuid4(),
        defuser_uuid=uuid4(),
        expert_uuid=None,
        game_uuid=uuid4(),
        start_time=Instant.now(),
        defuser_capabilities=PlayerCapabilities(player_name="test-defuser", player_type="ai"),
        expert_capabilities=None,
    )


@fixture
def step_record(
    experiment_descriptor: ExperimentDescriptor,
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
        session_id=experiment_descriptor.session_id,
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


@pytest.mark.anyio
async def test_step_record_serialization(step_record: ExperimentStep) -> None:
    """Test that a single step record can be serialized to JSON."""
    dumped = step_record.model_dump(mode="json")
    assert isinstance(dumped, dict)
    assert dumped["step"] == 1
    assert dumped["role"] == "defuser"

    json_bytes = orjson.dumps(dumped)
    assert len(json_bytes) > 0

    loaded_dict = orjson.loads(json_bytes)
    assert loaded_dict["step"] == 1


@pytest.mark.anyio
async def test_player_record_serialization(
    experiment_descriptor: ExperimentDescriptor,
    player_content: PlayerContent,
    step_record: ExperimentStep,
) -> None:
    """Test that a player record with multiple steps can be serialized."""
    step2 = step_record.model_copy(update={"step": 2, "timestamp": 2.0, "thoughts": "Second step"})

    player_record = ExperimentPlayerRecord(
        experiment_descriptor=experiment_descriptor,
        player_content=player_content,
        step_records=[step_record, step2],
        is_hard_crash=False,
    )

    dumped = player_record.model_dump(mode="json")
    assert isinstance(dumped, dict)
    assert len(dumped["step_records"]) == 2
    assert dumped["num_steps"] == 2

    json_bytes = orjson.dumps(dumped)
    assert len(json_bytes) > 100

    loaded_dict = orjson.loads(json_bytes)
    assert len(loaded_dict["step_records"]) == 2


def test_arrow_schema_derives_from_duckdb() -> None:
    """`arrow_schema_for` is derived from the DuckDB table, so its columns match name-for-name.

    Smoke-tests the in-memory derivation (and that every model column survives the round-trip).
    """
    for model in (ExperimentStep, ExperimentSummary):
        arrow_names = [field.name for field in arrow_schema_for(model)]
        # Column names from the generated CREATE TABLE, in declared order.
        ddl_lines = generate_duckdb_schema(model).splitlines()[1:-1]
        duckdb_names = [line.strip().split(" ", 1)[0] for line in ddl_lines]
        assert arrow_names == duckdb_names


def _build_player_record(
    descriptor: ExperimentDescriptor, content: PlayerContent, step: ExperimentStep
) -> ExperimentPlayerRecord:
    # The recorder stamps every step with the player's own uuid; mirror that so the footer's
    # player_uuid matches the step rows (the basis for ingest idempotency).
    step1 = step.model_copy(update={"player_uuid": content.uuid})
    step2 = step1.model_copy(update={"step": 2, "timestamp": 2.0, "thoughts": "Second step"})
    return ExperimentPlayerRecord(
        experiment_descriptor=descriptor,
        player_content=content,
        step_records=[step1, step2],
        is_hard_crash=False,
    )


@pytest.mark.anyio
async def test_recorder_saves_parquet_roundtrips(
    tmp_path: Path,
    experiment_descriptor: ExperimentDescriptor,
    player_content: PlayerContent,
    step_record: ExperimentStep,
) -> None:
    """The real recorder method writes a parquet file that round-trips back to the same record."""
    player_record = _build_player_record(experiment_descriptor, player_content, step_record)

    recorder = ExperimentPlayerRecorder(
        capabilities=PlayerCapabilities(player_name="test-defuser", player_type="ai")
    )
    recorder.output_dir = tmp_path
    await recorder.save_player_record_to_disk(player_record=player_record)

    output_path = (
        tmp_path / f"experiment-{experiment_descriptor.name}-{player_content.uuid}.parquet"
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
    assert loaded.git_sha == player_record.git_sha


def test_record_footer_rejects_unknown_format_version(
    tmp_path: Path,
    experiment_descriptor: ExperimentDescriptor,
    player_content: PlayerContent,
    step_record: ExperimentStep,
) -> None:
    """An unknown footer format_version fails loudly rather than silently mis-parsing."""
    record = _build_player_record(experiment_descriptor, player_content, step_record)
    footer = footer_from_player_record(record)
    footer[KEY_FORMAT_VERSION] = b"this-is-not-a-known-version"

    path = tmp_path / "bad-version.parquet"
    write_player_record_parquet(
        blobbed_steps=[blob_step(step) for step in record.step_records],
        footer=footer,
        output_path=path,
    )

    with pytest.raises(ValueError, match="format_version"):
        _ = read_record_footer(path)


@pytest.mark.anyio
async def test_recorder_skips_empty_record(
    tmp_path: Path, experiment_descriptor: ExperimentDescriptor, player_content: PlayerContent
) -> None:
    """A record with no steps writes nothing (no empty parquet file)."""
    empty_record = ExperimentPlayerRecord(
        experiment_descriptor=experiment_descriptor,
        player_content=player_content,
        step_records=[],
        is_hard_crash=False,
    )
    recorder = ExperimentPlayerRecorder(
        capabilities=PlayerCapabilities(player_name="test-defuser", player_type="ai")
    )
    recorder.output_dir = tmp_path
    await recorder.save_player_record_to_disk(player_record=empty_record)

    # Synchronous glob in a test assertion — not a hot path, anyio.Path is unwarranted here.
    assert list(tmp_path.glob("*.parquet")) == []  # noqa: ASYNC240


def _write_record_parquet(record: ExperimentPlayerRecord, path: Path) -> None:
    write_player_record_parquet(
        blobbed_steps=[blob_step(step) for step in record.step_records],
        footer=footer_from_player_record(record),
        output_path=path,
    )


def test_ingest_recorder_parquet_into_duckdb(
    tmp_path: Path, experiment_descriptor: ExperimentDescriptor, step_record: ExperimentStep
) -> None:
    """Recorder parquet merges straight into DuckDB; metadata comes from the footer; idempotent."""
    # Derive the player from the descriptor (as the recorder does) so identity keys line up.
    content = experiment_descriptor.get_player_content_by_role("defuser")
    record = _build_player_record(experiment_descriptor, content, step_record)
    record_path = tmp_path / f"experiment-{experiment_descriptor.name}-{content.uuid}.parquet"
    _write_record_parquet(record, record_path)

    db_path = tmp_path / "test.duckdb"
    ingest_kwargs = {"player_record_paths": [record_path], "db_path": db_path, "max_workers": 1}
    ingest_player_records(**ingest_kwargs)

    with duckdb.connect(db_path) as con:
        step_count = con.execute("SELECT COUNT(*) FROM experiment_step").fetchone()
        meta = con.execute(
            "SELECT session_id, gptnt_version, num_modules_solved FROM experiment_summary"
        ).fetchall()

    assert step_count is not None
    assert step_count[0] == 2
    assert len(meta) == 1
    assert str(meta[0][0]) == str(experiment_descriptor.session_id)
    assert meta[0][1] == record.gptnt_version

    # Idempotent: a second ingest of the same file adds nothing.
    ingest_player_records(**ingest_kwargs)
    with duckdb.connect(db_path) as con:
        again = con.execute("SELECT COUNT(*) FROM experiment_step").fetchone()
    assert again is not None
    assert again[0] == 2
