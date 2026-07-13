"""Fixtures for in-situ interactive integration tests (fake Redis + fake game, real services).

- `fake_redis_dsn` — an in-process fake Redis (sync; starts before anything connects)
- `fake_game`      — patches the game process manager + mocks the KTANE HTTP endpoints. Parametrise
                     its outcome indirectly: `@pytest.mark.parametrize("fake_game", ["detonated"],
                     indirect=True)`.
- `records_dir`    — the per-test directory the players' recorders write parquet records to
- `assembled`      — the live EM + game + 2 player services on the fake Redis
- `assembled_solo` — the same, but Defuser-only (no expert)

To debug by hand, the same pieces are importable directly:

    from tests._harness.fake_redis import fake_redis_server
    from tests._harness.fake_game import FakeKtaneGame
    from tests._harness.assembly import assembled_experiment
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from gptnt.experiments.recorder.local import ExperimentPlayerRecorder

from tests._harness.assembly import assembled_experiment
from tests._harness.fake_game import FakeKtaneGame
from tests._harness.fake_redis import fake_redis_server

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator
    from pathlib import Path

    import respx

    from tests._harness.assembly import AssembledExperiment


@pytest.fixture
def fake_redis_dsn() -> Iterator[str]:
    """An in-process fake Redis; yields its DSN."""
    with fake_redis_server() as dsn:
        yield dsn


@pytest.fixture
def fake_game(
    request: pytest.FixtureRequest, respx_mock: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> FakeKtaneGame:
    """Install the scripted KTANE game; outcome comes from an indirect param, default `solved`."""
    outcome = getattr(request, "param", "solved")
    game = FakeKtaneGame(outcome=outcome)
    game.install(respx_mock, monkeypatch)
    return game


@pytest.fixture
def records_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the players' recorder at a per-test directory and return it.

    `ExperimentPlayerRecorder.output_dir` is a class-attribute default frozen at import from
    `EXPERIMENT_RECORDER_OUTPUTS`; without this redirect a run's records leak into the repo's
    gitignored `output/` tree instead of a throwaway per-test dir, and nothing can assert on them.
    Patching the class attribute before the services assemble points every recorder here.
    """
    records = tmp_path.joinpath("records")
    records.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(ExperimentPlayerRecorder, "output_dir", records)
    monkeypatch.setattr(ExperimentPlayerRecorder, "observations_dir", records.joinpath("obs"))
    monkeypatch.setenv("EXPERIMENT_RECORDER_OUTPUTS", records.as_posix())
    return records


@pytest.fixture
async def assembled(
    fake_redis_dsn: str, fake_game: FakeKtaneGame, records_dir: Path
) -> AsyncIterator[AssembledExperiment]:
    """A live Defuser+Expert system (EM + game + 2 players) on the fake Redis, ready to run."""
    async with assembled_experiment(fake_redis_dsn) as experiment:
        yield experiment


@pytest.fixture
async def assembled_solo(
    fake_redis_dsn: str, fake_game: FakeKtaneGame, records_dir: Path
) -> AsyncIterator[AssembledExperiment]:
    """A live Defuser-only system (no expert) on the fake Redis, ready to run solo play."""
    async with assembled_experiment(fake_redis_dsn, expert_model=None) as experiment:
        yield experiment
