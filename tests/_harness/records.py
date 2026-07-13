"""Wait and read the parquet records a run wrote from the players' background save tasks."""

from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING

import anyio
from pyarrow import ArrowInvalid

from gptnt.experiments.models import ExperimentOutcome
from gptnt.experiments.recorder.parquet import read_record_footer

if TYPE_CHECKING:
    from pathlib import Path

    from gptnt.experiments.recorder.parquet import RecordFooter


def _readable_footers(records_dir: Path) -> list[RecordFooter]:
    """Every player record currently readable under `records_dir`.

    Skips a file a player's background save is still writing, since the runner reaches `done`
    before that save flushes and a half-written parquet raises on read. A `ValueError` (an unknown
    footer format version) is a genuine problem, not a mid-write file, so it propagates.
    """
    footers: list[RecordFooter] = []
    for path in sorted(records_dir.glob("experiment-*.parquet")):
        # A mid-write parquet raises `OSError`/`ArrowInvalid`; the next poll retries it.
        with suppress(OSError, ArrowInvalid):
            footers.append(read_record_footer(path))
    return footers


async def wait_for_record_footers(
    records_dir: Path, *, count: int = 1, fail_after: float = 20.0
) -> list[RecordFooter]:
    """Poll until at least `count` player records are on disk and return them.

    The player writes its parquet from a background task the runner does not await (see
    `PlayerService._stop_player_async`), so records land shortly after the session reaches `done`.
    """
    with anyio.fail_after(fail_after):
        while True:
            footers = _readable_footers(records_dir)
            if len(footers) >= count:
                return footers
            await anyio.sleep(0.1)


async def wait_for_recorded_outcome(
    records_dir: Path, *, fail_after: float = 20.0
) -> ExperimentOutcome:
    """Wait for a completed run's record and return the outcome the DuckDB ingest would read.

    Waits for a record carrying a final bomb state (the defuser stamps it on stop), then derives
    the canonical `ExperimentOutcome` from it.
    """
    with anyio.fail_after(fail_after):
        while True:
            stated = next(
                (
                    footer
                    for footer in _readable_footers(records_dir)
                    if footer.final_bomb_state is not None
                ),
                None,
            )
            if stated is not None:
                return ExperimentOutcome.from_bomb_state(
                    stated.final_bomb_state, is_hard_crash=stated.is_hard_crash
                )
            await anyio.sleep(0.1)
