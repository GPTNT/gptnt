"""Tests for building an ExperimentRecord from per-player records."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from pydantic_ai.result import RunUsage

from gptnt.experiments.instance import ExperimentInstance, PlayerContent
from gptnt.experiments.models import ExperimentPlayerRecord, ExperimentRecord, ExperimentStep
from gptnt.experiments.spec import ExperimentSpec
from gptnt.ktane.mission_spec import KtaneMissionSpec
from gptnt.players.actions import DoNothingAction
from gptnt.players.specification import PlayerCapabilities, PlayerProtocol

if TYPE_CHECKING:
    from uuid import UUID

pytestmark = pytest.mark.anyio


def _instance() -> ExperimentInstance:
    protocol = PlayerProtocol(
        role="defuser", communication_style="sync", is_playing_alone=False, include_manual=True
    )
    spec = ExperimentSpec(
        mission_spec=KtaneMissionSpec(
            seed=7, time_limit=300, num_strikes_allowed=3, components=["Wires"], optional_widgets=1
        ),
        mission_set="single_module",
        suite_name="test-suite",
        suite_revision=1,
        suite_digest="0" * 32,
        defuser_protocol=protocol,
        defuser_name="test-defuser",
        expert_protocol=PlayerProtocol(
            role="expert", communication_style="sync", is_playing_alone=False, include_manual=True
        ),
        expert_name="test-expert",
    )
    return ExperimentInstance.model_validate(
        spec.model_dump()
        | {
            "session_id": uuid4(),
            "defuser_uuid": uuid4(),
            "expert_uuid": uuid4(),
            "game_uuid": uuid4(),
            "defuser_capabilities": PlayerCapabilities(
                player_name="test-defuser", player_type="ai"
            ),
            "expert_capabilities": PlayerCapabilities(player_name="test-expert", player_type="ai"),
        }
    )


def _step(
    *, step: int, timestamp: float, role: str, player_uuid: UUID, session_id: UUID
) -> ExperimentStep:
    return ExperimentStep(
        step=step,
        timestamp=timestamp,
        role=role,
        session_id=session_id,
        player_uuid=player_uuid,
        player_name=f"test-{role}",
        output=DoNothingAction(),
        raw_output="DoNothing",
        input_messages=[],
        new_messages=[],
        bomb_state=None,
        observation=None,
        usage=RunUsage(requests=1, input_tokens=10, output_tokens=2),
        num_prompt_truncations=0,
        error_type=None,
        is_reflection=False,
    )


def _player_record(
    instance: ExperimentInstance, *, role: str, timestamps: list[float], is_hard_crash: bool
) -> ExperimentPlayerRecord:
    player_uuid = uuid4()
    content = PlayerContent(
        protocol=instance.defuser_protocol,
        name=f"test-{role}",
        uuid=player_uuid,
        capabilities=PlayerCapabilities(player_name=f"test-{role}", player_type="ai"),
    )
    steps = [
        _step(
            step=index,
            timestamp=stamp,
            role=role,
            player_uuid=player_uuid,
            session_id=instance.session_id,
        )
        for index, stamp in enumerate(timestamps)
    ]
    return ExperimentPlayerRecord(
        experiment_instance=instance,
        player_content=content,
        step_records=steps,
        is_hard_crash=is_hard_crash,
    )


async def test_from_player_records_aggregates_and_sorts_by_timestamp() -> None:
    instance = _instance()
    defuser = _player_record(instance, role="defuser", timestamps=[0, 2], is_hard_crash=False)
    expert = _player_record(instance, role="expert", timestamps=[1, 3], is_hard_crash=False)

    record = ExperimentRecord.from_player_records(player_records=[defuser, expert])

    assert len(record.player_records) == 2
    assert not record.is_hard_crash
    # Steps from both players, interleaved and sorted by timestamp.
    assert [step.timestamp for step in record.step_records] == [0, 1, 2, 3]


async def test_from_player_records_propagates_hard_crash() -> None:
    instance = _instance()
    healthy = _player_record(instance, role="defuser", timestamps=[0], is_hard_crash=False)
    crashed = _player_record(instance, role="expert", timestamps=[1], is_hard_crash=True)

    record = ExperimentRecord.from_player_records(player_records=[healthy, crashed])

    assert record.is_hard_crash
