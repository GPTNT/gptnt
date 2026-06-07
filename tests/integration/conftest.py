"""Fixtures for in-situ interactive integration tests (fake Redis + fake game, real services).

The fixtures are deliberately small and composable so they can be driven step-by-step in a REPL
or under `pytest -s` while debugging:

- `fake_redis_dsn` — an in-process fake Redis (sync; starts before anything connects)
- `fake_game`      — patches the game process manager + mocks the KTANE HTTP endpoints
- `assembled`      — the live EM + game + 2 player services on the fake Redis

To debug by hand, the same pieces are importable directly:

    from tests._harness.fake_redis import fake_redis_server
    from tests._harness.fake_game import FakeKtaneGame
    from tests._harness.assembly import assembled_experiment
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from tests._harness.assembly import assembled_experiment
from tests._harness.fake_game import FakeKtaneGame
from tests._harness.fake_redis import fake_redis_server

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

    import respx

    from tests._harness.assembly import AssembledExperiment


@pytest.fixture
def fake_redis_dsn() -> Iterator[str]:
    """An in-process fake Redis; yields its DSN."""
    with fake_redis_server() as dsn:
        yield dsn


@pytest.fixture
def fake_game(respx_mock: respx.MockRouter, monkeypatch: pytest.MonkeyPatch) -> FakeKtaneGame:
    """Install the scripted KTANE game (patches the process manager + mocks the HTTP endpoints)."""
    game = FakeKtaneGame()
    game.install(respx_mock, monkeypatch)
    return game


@pytest.fixture
def records_dir() -> Path:
    """The throwaway directory experiment records are written to (see root conftest)."""
    return Path(os.environ["EXPERIMENT_RECORDER_OUTPUTS"])


@pytest.fixture
async def assembled(
    fake_redis_dsn: str,
    fake_game: FakeKtaneGame,  # noqa: ARG001
) -> AsyncIterator[AssembledExperiment]:
    """A live Defuser+Expert system (EM + game + 2 players) on the fake Redis, ready to run."""
    async with assembled_experiment(fake_redis_dsn) as experiment:
        yield experiment
