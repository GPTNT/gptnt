from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from gptnt.cli.__main__ import build_app
from gptnt.interactive.services.experiment_manager.experiment_runner import (
    AsyncExperimentRunner,
    ExperimentState,
)

from tests._cli_runner import invoke_cli
from tests._harness.records import wait_for_record_footers, wait_for_recorded_outcome

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

    from tests._harness.assembly import AssembledExperiment
    from tests._harness.fake_game import FakeKtaneGame

# Manual debugging (see where a run stalls, without output capture):
#   uv run pytest tests/integration/test_smoke.py -s -o addopts="" -p no:sugar --no-header
# The full-run family exercises the orchestration over `FakeKtaneGame`, a scripted single-module
# phase machine with no real timing or frame-buffer decoding. A green run is evidence about the
# service plumbing, not that the benchmark starts against the real KTANE binary (a `requires_game`
# run covers that), and it drives the dummy players, not model I/O.

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


@pytest.mark.slow
async def test_full_run_solved(
    assembled: AssembledExperiment, fake_game: FakeKtaneGame, records_dir: Path
) -> None:
    """A full run reaches done, the defuser acts on the bomb, and the record reads solved."""
    session = await assembled.run_to_completion(assembled.build_spec())

    assert session.state == ExperimentState.done
    assert not session.is_hard_crash
    assert fake_game.hits.get("/action", 0) > 0, "the defuser never acted on the bomb"

    outcome = await wait_for_recorded_outcome(records_dir)
    assert outcome.is_solved
    assert not outcome.is_detonated


@pytest.mark.slow
@pytest.mark.parametrize("fake_game", ["detonated"], indirect=True)
async def test_full_run_detonated(
    assembled: AssembledExperiment, fake_game: FakeKtaneGame, records_dir: Path
) -> None:
    """A detonated bomb ends the run withoutß a hard crash, and records it."""
    session = await assembled.run_to_completion(assembled.build_spec())

    assert session.state == ExperimentState.done
    assert not session.is_hard_crash, "detonation is a game-over end, not a hard crash"

    outcome = await wait_for_recorded_outcome(records_dir)
    assert outcome.is_detonated
    assert not outcome.is_solved


@pytest.mark.slow
@pytest.mark.parametrize("fake_game", ["timed_out"], indirect=True)
async def test_full_run_timeout(
    assembled: AssembledExperiment, fake_game: FakeKtaneGame, records_dir: Path
) -> None:
    """A bomb that runs out of time ends the run and records a timed-out outcome."""
    session = await assembled.run_to_completion(assembled.build_spec())

    assert session.state == ExperimentState.done
    assert not session.is_hard_crash

    outcome = await wait_for_recorded_outcome(records_dir)
    assert outcome.is_timed_out
    assert not outcome.is_solved


@pytest.mark.slow
async def test_full_run_solo(
    assembled_solo: AssembledExperiment, fake_game: FakeKtaneGame, records_dir: Path
) -> None:
    """Solo play drives the runner's `expert is None` branches from start to a recorded outcome."""
    spec = assembled_solo.build_spec()
    assert spec.expert_name is None, "solo spec must carry no expert"

    session = await assembled_solo.run_to_completion(spec)

    assert session.state == ExperimentState.done
    assert not session.is_hard_crash
    assert (await wait_for_recorded_outcome(records_dir)).is_solved


@pytest.mark.slow
async def test_full_run_async(
    assembled: AssembledExperiment, fake_game: FakeKtaneGame, records_dir: Path
) -> None:
    """An async-style run selects the `AsyncExperimentRunner` and reaches a recorded outcome."""
    spec = assembled.build_spec(communication_style="async")
    session = await assembled.run_to_completion(spec)

    # Assert the runner type so a silent fallback to the sync runner cannot pass this vacuously.
    assert isinstance(session.experiment_runner, AsyncExperimentRunner)
    assert session.state == ExperimentState.done
    assert not session.is_hard_crash
    assert fake_game.hits.get("/action", 0) > 0
    assert (await wait_for_recorded_outcome(records_dir)).is_solved


@pytest.mark.slow
async def test_run_to_results_chain(
    assembled: AssembledExperiment, fake_game: FakeKtaneGame, records_dir: Path, tmp_path: Path
) -> None:
    """A run's records ingest into DuckDB and surface through `results` with the right outcome.

    Guards against drift between the outcome the runner records and what `build-db`/`results` read.
    """
    session = await assembled.run_to_completion(assembled.build_spec())
    assert session.state == ExperimentState.done
    _ = await wait_for_record_footers(records_dir, count=2)

    db_path = tmp_path.joinpath("experiments.duckdb")
    built = invoke_cli(build_app(), ["build-db", str(records_dir), "--output", str(db_path)])
    assert built.exit_code == 0, built.output

    shown = invoke_cli(build_app(), ["results", str(db_path)])
    assert shown.exit_code == 0, shown.output
    assert "solved" in shown.output
