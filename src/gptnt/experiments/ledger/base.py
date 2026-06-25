from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Iterable

ExperimentStatus = Literal["done", "failed", "not_attempted", "running"]


class Source(StrEnum):
    """Where to read experiment-completion truth from.

    `local` (the default) reads the on-disk experiment outputs. `wandb` is a cross-machine
    aggregator and requires `WANDB_ENTITY`/`WANDB_PROJECT` in the environment and the `wandb` extra
    installed.
    """

    local = "local"
    wandb = "wandb"


@runtime_checkable
class CompletionLedger(Protocol):
    """Answers 'which of these experiments are already done?' for a set of attempt names."""

    def status_for(self, attempt_names: Iterable[str]) -> dict[str, ExperimentStatus]:
        """Map every given attempt name to its status."""
        ...

    def completed(self, attempt_names: Iterable[str]) -> set[str]:
        """The subset of attempt names that are done and valid (safe to skip re-running).

        Implementations MAY prune stale state while answering (the W&B ledger marks invalid remote
        runs `old` so a run left in a bad state doesn't block a re-run); the local ledger is a pure
        read. Both decide "done & valid" through the same `is_valid_outcome`, so the answer itself
        never depends on the source.
        """
        ...
