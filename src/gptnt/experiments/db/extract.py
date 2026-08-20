from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Any

import structlog

from gptnt.common.logger import ProgressSentinel, with_default_progress
from gptnt.experiments.db.schema import EXPORT_CONTEXT_MARKER
from gptnt.experiments.models import ExperimentSummary, is_valid_outcome
from gptnt.experiments.recorder.parquet import (
    KEY_PLAYER_UUID,
    KEY_SESSION_ID,
    read_footer_kv,
    read_record_footer,
    read_session_id_from_parquet,
)
from gptnt.provenance import Provenance

if TYPE_CHECKING:
    from pathlib import Path

    import duckdb
    from pydantic import BaseModel
    from rich.progress import Progress

    from gptnt.experiments.recorder.parquet import RecordFooter

logger = structlog.get_logger()

type DumpedExperimentMetadata = dict[str, Any]


def _find_conflicting_fields(canonical: BaseModel, peers: list[BaseModel]) -> list[str]:
    """Name fields whose Pydantic values differ from the canonical model."""
    canonical_fields = canonical.model_dump(exclude_computed_fields=True)
    peer_fields = [peer.model_dump(exclude_computed_fields=True) for peer in peers]
    return [
        field_name
        for field_name, canonical_value in canonical_fields.items()
        if any(peer[field_name] != canonical_value for peer in peer_fields)
    ]


def _find_conflicting_summary_fields(footers: list[RecordFooter]) -> list[str]:
    """Name every summary identity field that differs among player footers."""
    canonical, *peers = footers
    conflicting_fields = _find_conflicting_fields(
        Provenance.model_validate(canonical.model_dump()),
        [Provenance.model_validate(peer.model_dump()) for peer in peers],
    )
    conflicting_fields.extend(
        _find_conflicting_fields(canonical.instance, [peer.instance for peer in peers])
    )
    if any(peer.instance.fingerprint != canonical.instance.fingerprint for peer in peers):
        conflicting_fields.append("ExperimentSpec fingerprint")
    return conflicting_fields


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
    return is_valid_outcome(
        outcome=final_bomb_state.outcome,
        is_hard_crash=any(footer.is_hard_crash for footer in footers),
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
    canonical_provenance = Provenance.model_validate(canonical.model_dump())

    conflicting_fields = _find_conflicting_summary_fields(footers)
    if conflicting_fields:
        raise ValueError(
            "Grouped experiment files disagree on summary identity: "
            f"{', '.join(conflicting_fields)}"
        )

    return ExperimentSummary.from_instance_and_bomb_state(
        instance=canonical.instance,
        final_bomb_state=final_bomb_state,
        is_hard_crash=any(footer.is_hard_crash for footer in footers),
        provenance=canonical_provenance,
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
