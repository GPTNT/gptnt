from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, override

from gptnt.experiments.db._extract import compute_experiment_validity
from gptnt.experiments.ledger.base import CompletionLedger, ExperimentStatus

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

_UUID_LENGTH = 36
_PREFIX = "experiment-"


@dataclass(kw_only=True)
class LocalLedger(CompletionLedger):
    """Completion ledger backed by the recorder's on-disk JSON outputs.

    Reads completion straight from the recorded outputs — the same `attempt_name` key W&B uses, so
    a local lookup is a drop-in for the W&B query. Needs no DB build: it groups the
    `experiment-*.json` files by attempt name and reuses the DB layer's mmap tail-scan + validity
    check.
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
        """Group every output file by attempt name and classify each group via disk validity."""
        if not self.output_dir.exists():
            return {}

        grouped: dict[str, list[Path]] = defaultdict(list)
        for path in self.output_dir.rglob(f"{_PREFIX}*.json"):
            grouped[_attempt_name_from_path(path)].append(path)

        return {
            attempt_name: ("done" if compute_experiment_validity(paths) else "failed")
            for attempt_name, paths in grouped.items()
        }


def _attempt_name_from_path(path: Path) -> str:
    """Recover the attempt name from an `experiment-{attempt_name}-{uuid}.json` filename."""
    return path.stem[len(_PREFIX) : -(_UUID_LENGTH + 1)]
