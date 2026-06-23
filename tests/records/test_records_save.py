from pathlib import Path
from uuid import uuid4

import anyio
import orjson
import pytest
from pydantic_ai import BinaryContent, ModelMessage, ModelRequest, ModelResponse, TextPart
from pydantic_ai.messages import SystemPromptPart, UserPromptPart
from pydantic_ai.result import RunUsage
from pytest_cases import fixture
from whenever import Instant

from gptnt.core.ktane.mission_spec import KtaneMissionSpec
from gptnt.core.ktane.state.bomb import BombState
from gptnt.core.players.actions import DoNothingAction
from gptnt.core.players.observation_handler import Observation
from gptnt.core.specification import PlayerCapabilities, PlayerProtocol
from gptnt.experiments.descriptor import ExperimentDescriptor, PlayerContent
from gptnt.experiments.models import ExperimentPlayerRecord, ExperimentStepRecord
from gptnt.experiments.spec import ExperimentSpec


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
        condition="single_module",
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
) -> ExperimentStepRecord:
    """Create a minimal step record with inline observation."""
    return ExperimentStepRecord(
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
async def test_step_record_serialization(step_record: ExperimentStepRecord) -> None:
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
    step_record: ExperimentStepRecord,
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


@pytest.mark.anyio
async def test_save_player_record_to_file(
    tmp_path: Path,
    experiment_descriptor: ExperimentDescriptor,
    player_content: PlayerContent,
    step_record: ExperimentStepRecord,
) -> None:
    """Test saving a player record to disk creates a non-empty valid JSON file."""
    step2 = step_record.model_copy(update={"step": 2, "timestamp": 2.0})

    player_record = ExperimentPlayerRecord(
        experiment_descriptor=experiment_descriptor,
        player_content=player_content,
        step_records=[step_record, step2],
        is_hard_crash=False,
    )

    output_path = tmp_path / f"experiment-{experiment_descriptor.name}-{player_content.uuid}.json"

    dumped = player_record.model_dump(mode="json")
    json_bytes = orjson.dumps(dumped)
    _ = output_path.write_bytes(json_bytes)

    assert output_path.exists()
    assert output_path.stat().st_size > 100

    loaded_bytes = output_path.read_bytes()
    loaded_dict = orjson.loads(loaded_bytes)
    assert len(loaded_dict["step_records"]) == 2
    assert loaded_dict["num_steps"] == 2

    reconstructed = ExperimentPlayerRecord.model_validate(loaded_dict)
    assert len(reconstructed.step_records) == 2
    assert reconstructed.num_steps == 2


@pytest.mark.anyio
async def test_save_with_rebuild_observations(
    tmp_path: Path,
    experiment_descriptor: ExperimentDescriptor,
    player_content: PlayerContent,
    step_record: ExperimentStepRecord,
) -> None:
    """Test saving when observations need to be rebuilt."""
    player_record = ExperimentPlayerRecord(
        experiment_descriptor=experiment_descriptor,
        player_content=player_content,
        step_records=[step_record],
        is_hard_crash=False,
    )

    rebuilt_record = await player_record.rebuild_with_observations()

    dumped = rebuilt_record.model_dump(mode="json")
    json_bytes = orjson.dumps(dumped)
    assert len(json_bytes) > 100

    output_path = tmp_path / f"test-record-{uuid4()}.json"
    _ = output_path.write_bytes(json_bytes)

    assert output_path.exists()
    assert output_path.stat().st_size > 100


@pytest.mark.anyio
async def test_save_with_anyio_file_operations(
    tmp_path: Path,
    experiment_descriptor: ExperimentDescriptor,
    player_content: PlayerContent,
    step_record: ExperimentStepRecord,
) -> None:
    """Test saving using anyio async file operations."""
    step2 = step_record.model_copy(update={"step": 2, "timestamp": 2.0})

    player_record = ExperimentPlayerRecord(
        experiment_descriptor=experiment_descriptor,
        player_content=player_content,
        step_records=[step_record, step2],
        is_hard_crash=False,
    )

    output_path = tmp_path / f"experiment-{experiment_descriptor.name}-{player_content.uuid}.json"

    async with await anyio.open_file(output_path, "wb") as output_file:
        output_data = orjson.dumps(player_record.model_dump(mode="json"))
        assert output_data
        _ = await output_file.write(output_data)

    assert output_path.exists()
    assert output_path.stat().st_size > 100

    loaded_bytes = output_path.read_bytes()
    loaded_dict = orjson.loads(loaded_bytes)
    assert len(loaded_dict["step_records"]) == 2
    assert loaded_dict["num_steps"] == 2

    reconstructed = ExperimentPlayerRecord.model_validate(loaded_dict)
    assert len(reconstructed.step_records) == 2
    assert reconstructed.num_steps == 2
