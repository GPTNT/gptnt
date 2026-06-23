from __future__ import annotations

from typing import TYPE_CHECKING

from gptnt.experiments.ledger.base import CompletionLedger, Source
from gptnt.experiments.ledger.local import LocalLedger
from gptnt.experiments.ledger.wandb import WandbLedger, resolve_wandb_path

if TYPE_CHECKING:
    from pathlib import Path

    from gptnt.experiments.spec import ExperimentSpec


def resolve_ledger(source: Source, *, output_dir: Path) -> CompletionLedger:
    """Build the ledger for the chosen source (local by default; W&B only when asked)."""
    if source is Source.local:
        return LocalLedger(output_dir=output_dir)

    return WandbLedger(wandb_path=resolve_wandb_path())


def filter_experiments(
    specs: list[ExperimentSpec], *, source: Source, output_dir: Path
) -> list[ExperimentSpec]:
    """Drop the specs that are already done, per the chosen completion source.

    The single front door used by both `submit` and the `run`/`doctor` resume check, so the two can
    never disagree about what counts as 'already done'.
    """
    ledger = resolve_ledger(source, output_dir=output_dir)
    done = ledger.completed(spec.attempt_name for spec in specs)
    return [spec for spec in specs if spec.attempt_name not in done]
