from dataclasses import dataclass, field
from typing import override

import anyio
import pytest
from pydantic_ai import RunUsage
from whenever import Instant

from gptnt.ktane.actions import (
    GameActionType,
    GameActionTypeWithExtras,
    KtaneBaseAction,
    KtaneGameplayInput,
    RelativeCoordinate,
)
from gptnt.players.actions import (
    DoNothingAction,
    InteractGameAction,
    PlayerOutputType,
    SendMessageAction,
)
from gptnt.players.base_action_dispatcher import BaseActionDispatcher
from gptnt.players.observation_handler import ObservationHandler
from gptnt.players.result import AgentCallResult


@dataclass(kw_only=True)
class RecordingActionDispatcher(BaseActionDispatcher):
    """Record when an outbound operation reaches its concrete dispatcher."""

    operation_started_at: Instant | None = field(default=None, init=False)

    @override
    async def send_dialogue_message(self, message: str) -> None:
        self.operation_started_at = Instant.now()
        await anyio.sleep(0.01)

    @override
    async def send_game_action(
        self, action: KtaneBaseAction[GameActionTypeWithExtras, RelativeCoordinate]
    ) -> None:
        self.operation_started_at = Instant.now()
        await anyio.sleep(0.01)


def _agent_result(output: PlayerOutputType) -> AgentCallResult[PlayerOutputType]:
    return AgentCallResult[PlayerOutputType](
        output=output, thoughts=None, usage=RunUsage(), new_messages=[]
    )


def _dispatcher() -> RecordingActionDispatcher:
    return RecordingActionDispatcher(
        observation_handler=ObservationHandler(interaction_location_method="coordinates")
    )


@pytest.mark.anyio
async def test_do_nothing_timestamp_is_captured_when_processed() -> None:
    dispatcher = _dispatcher()
    before = Instant.now()

    dispatched = await dispatcher.direct_output_from_agent(_agent_result(DoNothingAction()))

    assert before <= dispatched.dispatched_at <= Instant.now()
    assert isinstance(dispatched.output, DoNothingAction)


@pytest.mark.anyio
async def test_message_timestamp_precedes_dispatch_delay() -> None:
    dispatcher = _dispatcher()

    dispatched = await dispatcher.direct_output_from_agent(
        _agent_result(SendMessageAction(message="Check the wires"))
    )

    assert dispatcher.operation_started_at is not None
    assert dispatched.dispatched_at <= dispatcher.operation_started_at
    assert isinstance(dispatched.output, SendMessageAction)


@pytest.mark.anyio
async def test_game_action_timestamp_precedes_dispatch_delay() -> None:
    dispatcher = _dispatcher()
    output = InteractGameAction[RelativeCoordinate](action=GameActionType.zoom_out)

    dispatched = await dispatcher.direct_output_from_agent(_agent_result(output))

    assert dispatcher.operation_started_at is not None
    assert dispatched.dispatched_at <= dispatcher.operation_started_at
    assert isinstance(dispatched.output, KtaneGameplayInput)
