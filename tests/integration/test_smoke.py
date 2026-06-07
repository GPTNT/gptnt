"""First integration test (the "floor"): real services assemble on fake Redis and matchmake.

This isolates the parts that MUST work for the benchmark to run at all — service startup,
heartbeat registration, and matchmaking — by mocking `Session.run` so it does NOT drive the
full game loop. That keeps the test robust and makes a stall easy to localise.

Manual debugging (run without output capture so you can see where it stalls)::

    uv run pytest tests/integration/test_smoke.py -s -o addopts="" -p no:sugar --no-header

Where a stall localises to:
- never reaches the body  -> the `assembled` fixture (service startup) is stuck
- reaches `wait_until_ready` timeout -> a service never registered as ready (heartbeats /
  the game's /health -> main_menu transition); inspect `assembled.experiment_manager`
  `.connected_services` / `.ready_games` / `.ready_players`
- past ready but no session -> matchmaking (`_try_match_experiments` / name matching)

The composable pieces are importable for a REPL session too — see `tests/integration/conftest.py`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import anyio
import pytest

from gptnt.interactive.services.experiment_manager.experiment_runner import ExperimentState

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

    from tests._harness.assembly import AssembledExperiment

pytestmark = [pytest.mark.anyio, pytest.mark.integration]


async def test_services_register_and_matchmake(
    assembled: AssembledExperiment, mocker: MockerFixture
) -> None:
    """EM + game + 2 players register over fake Redis; a submitted spec is matched to a session."""
    # Mock the experiment run itself — this test only covers assembly + registration + matchmaking.
    _ = mocker.patch(
        "gptnt.interactive.services.experiment_manager.session.Session.run", autospec=True
    )

    await assembled.wait_until_ready(timeout=8)

    spec = assembled.build_spec()
    assembled.experiment_manager.specs.add(spec)
    await assembled.experiment_manager.try_match_experiments()

    sessions = assembled.experiment_manager.active_sessions
    assert len(sessions) == 1, "matchmaking did not create a session"
    session = next(iter(sessions))
    assert session.spec == spec
    assert session.defuser.uuid == assembled.defuser.uuid
    assert session.game.uuid == assembled.game.uuid


def _is_set(obj: object, name: str) -> object:
    """Best-effort `event.is_set()` for a named attribute, or `"?"` if absent."""
    event = getattr(obj, name, None)
    return getattr(event, "is_set", lambda: "?")()


def _snapshot(session: object, game: object) -> str:
    """Defensive one-line trace of runner + fake-game state for localising a stall."""
    runner = getattr(session, "experiment_runner", None)
    watcher = getattr(runner, "game_state_watcher", None)
    defuser_watcher = getattr(runner, "defuser_state_watcher", None)

    return (
        f"runner={getattr(getattr(runner, 'state', None), 'name', '?')} "
        f"game.phase={getattr(game, 'phase', '?')} hits={getattr(game, 'hits', '?')} "
        f"timesteps={getattr(game, 'timesteps', '?')} actions={getattr(game, 'actions_sent', '?')} "
        f"lights_off={_is_set(watcher, 'lights_are_off_event')} "
        f"lights_on={_is_set(watcher, 'first_lights_on_event')} "
        f"game_over={_is_set(watcher, 'good_game_over_event')} "
        f"defuser_waiting={_is_set(defuser_watcher, 'is_first_waiting_for_turn')}"
    )


async def test_full_experiment_runs_to_completion(
    assembled: AssembledExperiment, fake_game: object
) -> None:
    """GOLD: drive the fake game to completion and assert the experiment finishes cleanly.

    Prints a state trace each time the runner/game phase changes so a stall localises to a phase.
    """

    await assembled.wait_until_ready(timeout=8)

    spec = assembled.build_spec()
    assembled.experiment_manager.specs.add(spec)
    await assembled.experiment_manager.try_match_experiments()
    session = next(iter(assembled.experiment_manager.active_sessions))

    last = ""
    with anyio.fail_after(50):
        while session.state != ExperimentState.done:
            snap = _snapshot(session, fake_game)
            if snap != last:
                last = snap
            await anyio.sleep(0.1)

    assert session.state == ExperimentState.done
    assert not session.is_hard_crash
