"""Tests for experiment heartbeat state watchers."""

from uuid import uuid4

import pytest

from gptnt.common.async_ops import Event
from gptnt.interactive.services.heartbeat.events import ReadyState
from gptnt.interactive.services.heartbeat.watcher import GameStateWatcher
from gptnt.ktane.state.game import GameState


def _game_watcher(*, state: GameState, ready_state: ReadyState) -> GameStateWatcher:
    """Build a watcher for testing terminal state signals without a Redis connection."""
    watcher = object.__new__(GameStateWatcher)
    watcher.service_uuid = uuid4()
    watcher._service_state = state
    watcher.ready_state = ready_state
    watcher.update_interval = 0.01
    watcher.good_game_over_event = Event()
    watcher.game_over_event = Event()
    return watcher


@pytest.mark.anyio
async def test_game_watcher_signals_terminal_event_after_a_normal_finish() -> None:
    watcher = _game_watcher(state=GameState.game_ended, ready_state=ReadyState.ready)

    await watcher.wait_for_game_over(fail_after=1)

    assert watcher.good_game_over_event.is_set()
    assert watcher.game_over_event.is_set()


@pytest.mark.anyio
async def test_game_watcher_signals_terminal_event_after_a_hard_crash() -> None:
    watcher = _game_watcher(state=GameState.lights_on, ready_state=ReadyState.not_ready)

    await watcher.wait_for_game_over(fail_after=1)

    assert watcher.game_over_event.is_set()
