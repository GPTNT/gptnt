from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Any

import structlog

from gptnt.common.logger import ProgressSentinel, with_default_progress
from gptnt.experiments.db.schema import EXPORT_CONTEXT_MARKER
from gptnt.experiments.models import ExperimentSummary, is_valid_experiment
from gptnt.experiments.recorder.parquet import (
    KEY_PLAYER_UUID,
    KEY_SESSION_ID,
    read_footer_kv,
    read_record_footer,
    read_session_id_from_parquet,
)

if TYPE_CHECKING:
    from pathlib import Path

    import duckdb
    from rich.progress import Progress

    from gptnt.experiments.recorder.parquet import RecordFooter

logger = structlog.get_logger()

type DumpedExperimentMetadata = dict[str, Any]


def validity_from_footers(footers: list[RecordFooter]) -> bool:
    """Whether a group of player footers forms a valid, completed experiment.

    Valid means no hard crash and a good ending (solved, or a clean strike-/time-out). An
    experiment that never reached a bomb state is not valid. The final bomb state lives only in the
    defuser's footer (the expert never observes the bomb), so we take the first non-null one. This
    is the same notion of validity the DB ingestion stamps, so disk-only callers (the local ledger,
    local cleanup) and the DB agree.
    """
    final_bomb_state = next(
        (footer.final_bomb_state for footer in footers if footer.final_bomb_state is not None),
        None,
    )
    if final_bomb_state is None:
        return False
    return is_valid_experiment(
        is_hard_crash=any(footer.is_hard_crash for footer in footers),
        final_bomb_state=final_bomb_state,
    )


def compute_experiment_validity(paths: list[Path]) -> bool:
    """Whether the grouped player files form a valid, completed experiment.

    Reads each file's footer exactly once.
    """
    return validity_from_footers([read_record_footer(path) for path in paths])


def extract_metadata_from_paths(paths: list[Path]) -> DumpedExperimentMetadata:
    """Build the experiment metadata for a group of player files, entirely from their footers.

    Parsed into an ExperimentSummary and dumped back to a dict so we only return JSON-serialisable
    data and keep the DB layer decoupled from the internal data model.
    """
    footers = [read_record_footer(path) for path in paths]
    final_bomb_state = next(
        (footer.final_bomb_state for footer in footers if footer.final_bomb_state is not None),
        None,
    )
    assert final_bomb_state is not None, "No bomb state found in any of the provided files"

    canonical = footers[0]
    return ExperimentSummary.from_descriptor_and_bomb_state(
        descriptor=canonical.descriptor,
        final_bomb_state=final_bomb_state,
        is_hard_crash=any(footer.is_hard_crash for footer in footers),
        gptnt_version=canonical.gptnt_version,
        git_sha=canonical.git_sha,
    ).model_dump(context={"mode": EXPORT_CONTEXT_MARKER})


def group_by_unique_experiment(file_paths: list[Path]) -> dict[str, list[Path]]:
    """Group player files into experiments by footer `session_id` — independent of the filename."""
    grouped: dict[str, list[Path]] = defaultdict(list)
    for path in file_paths:
        grouped[read_session_id_from_parquet(path)].append(path)
    return grouped


@with_default_progress()
def filter_existing_experiments(
    file_paths: list[Path],
    *,
    connection: duckdb.DuckDBPyConnection,
    progress: Progress = ProgressSentinel,
) -> list[Path]:
    """Return only the player files not yet ingested.

    Dedupes on the footer `(session_id, player_uuid)` against the rows already in
    `experiment_step` so ingestion is idempotent and independent of the filename scheme.
    """
    assert progress is not None
    task = progress.add_task("Checking for existing experiments in DB", total=None)

    if not file_paths:
        progress.update(task, completed=1, total=1)
        return []

    existing: set[tuple[str, str]] = {
        (str(row[0]), str(row[1]))
        for row in connection.execute(
            "SELECT DISTINCT session_id, player_uuid FROM experiment_step"
        ).fetchall()
    }

    new_paths = []
    for path in file_paths:
        footer = read_footer_kv(path)
        key = (footer[KEY_SESSION_ID].decode(), footer[KEY_PLAYER_UUID].decode())
        if key not in existing:
            new_paths.append(path)

    progress.update(task, completed=1, total=1)
    return new_paths
