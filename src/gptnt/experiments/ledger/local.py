from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, override

from gptnt.experiments.db._extract import validity_from_footers
from gptnt.experiments.ledger.base import CompletionLedger, ExperimentStatus
from gptnt.experiments.recorder.parquet import read_record_footer

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from gptnt.experiments.recorder.parquet import RecordFooter

_RECORD_GLOB = "experiment-*.parquet"


@dataclass(kw_only=True)
class LocalLedger(CompletionLedger):
    """Completion ledger backed by the recorder's on-disk parquet outputs.

    Reads completion straight from the recorded outputs — the same `attempt_name` key W&B uses, so
    a local lookup is a drop-in for the W&B query. Needs no DB build: it groups the
    `experiment-*.parquet` files by the attempt name in their footer (canonical, independent of the
    filename) and reuses the DB layer's footer-based validity check.
    """

    output_dir: Path

    @override
    def status_for(self, attempt_names: Iterable[str]) -> dict[str, ExperimentStatus]:
        """Map each attempt name to `done`/`failed`/`not_attempted` from disk."""
        scanned = self._scan()
        return {name: scanned.get(name, "not_attempted") for name in attempt_names}

    @override
    def completed(self, attempt_names: Iterable[str]) -> set[str]:
        """The attempt names with a valid, completed set of outputs on disk."""
        statuses = self.status_for(attempt_names)
        return {name for name, status in statuses.items() if status == "done"}

    def _scan(self) -> dict[str, ExperimentStatus]:
        """Group every output footer by its attempt name and classify each group by validity.

        Reads each file's footer once and keys off `descriptor.name` — robust to whatever the
        filename happens to be — then reuses the same footer-based validity the DB ingestion uses.
        """
        if not self.output_dir.exists():
            return {}

        grouped: dict[str, list[RecordFooter]] = defaultdict(list)
        for path in self.output_dir.rglob(_RECORD_GLOB):
            footer = read_record_footer(path)
            grouped[footer.descriptor.name].append(footer)

        return {
            attempt_name: ("done" if validity_from_footers(footers) else "failed")
            for attempt_name, footers in grouped.items()
        }
