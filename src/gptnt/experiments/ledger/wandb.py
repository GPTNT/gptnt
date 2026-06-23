from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, override

from gptnt.experiments.ledger.base import CompletionLedger
from gptnt.experiments.wandb_runs import (
    cleanup_wandb_runs,
    collate_runs_per_experiment_per_game,
    get_runs_from_wandb,
    is_run_valid,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from pydantic import UUID4
    from wandb.apis.public import Run

    from gptnt.experiments.ledger.base import ExperimentStatus
    from gptnt.experiments.wandb_runs import CollatedRuns


def wandb_path_or_none() -> str | None:
    """The `entity/project` from the environment, or None when either var is unset.

    `wandb` itself reads `WANDB_ENTITY`/`WANDB_PROJECT` from the environment, so we read them the
    same way.
    """
    entity = os.environ.get("WANDB_ENTITY")
    project = os.environ.get("WANDB_PROJECT")
    if entity and project:
        return f"{entity}/{project}"
    return None


def resolve_wandb_path() -> str:
    """The `entity/project` path, or raise with a fix hint when the environment is incomplete."""
    path = wandb_path_or_none()
    if path is None:
        raise RuntimeError(
            "W&B source selected but WANDB_ENTITY and WANDB_PROJECT are not both set; "
            "set them (and install the wandb extra), or use the default --source local"
        )
    return path


@dataclass(kw_only=True)
class WandbLedger(CompletionLedger):
    """Completion ledger backed by W&B runs, keyed by `config.attempt_name`."""

    wandb_path: str

    @override
    def status_for(self, attempt_names: Iterable[str]) -> dict[str, ExperimentStatus]:
        """Classify each attempt name from its W&B runs (done/running/failed/not_attempted)."""
        names = list(attempt_names)
        collated = self._gather(names, include_running=True, include_old=True)
        return {name: _experiment_status(collated.get(name, {})) for name in names}

    @override
    def completed(self, attempt_names: Iterable[str]) -> set[str]:
        """The attempt names already validly on W&B, cleaning up stale/invalid runs first.

        Mirrors the historical resume behaviour: gather → mark invalid runs old → re-gather, so a
        run left in a bad state does not block a re-run.
        """
        names = list(attempt_names)
        collated = self._gather(names)
        if not collated:
            return set()
        cleanup_wandb_runs(collated)
        return set(self._gather(names))

    def _gather(
        self, attempt_names: list[str], *, include_running: bool = False, include_old: bool = False
    ) -> CollatedRuns:
        """Fetch the runs for these attempt names and collate them by attempt → session."""
        if not attempt_names:
            return {}
        runs = get_runs_from_wandb(
            self.wandb_path,
            additional_filters=[
                {"$or": [{"config.attempt_name": name} for name in attempt_names]}
            ],
            per_page=1000,
            include_running=include_running,
            include_old=include_old,
        )
        if len(runs) == 0:
            return {}
        return collate_runs_per_experiment_per_game(runs)


def _experiment_status(sessions: dict[UUID4, list[Run]]) -> ExperimentStatus:
    """Roll the per-session statuses for one experiment into a single status."""
    if not sessions:
        return "not_attempted"
    session_statuses = {_session_status(runs) for runs in sessions.values()}
    if "done" in session_statuses:
        return "done"
    if "running" in session_statuses:
        return "running"
    return "failed"


def _session_status(session_runs: list[Run]) -> ExperimentStatus:
    """Aggregate status for a single session's runs."""
    if any(tag == "old" for run in session_runs for tag in (run.tags or [])):
        return "failed"
    states = {run.state for run in session_runs}
    if states & {"running", "pending"}:
        return "running"
    if states == {"finished"} and all(is_run_valid(run) for run in session_runs):
        return "done"
    return "failed"
