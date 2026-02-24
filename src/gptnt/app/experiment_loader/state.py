from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import structlog

from gptnt.app.experiment_loader.scanner import (
    ScannedExperiment,
    scan_experiments_from_directory,
    validate_scanned_experiments_with_wandb,
)

if TYPE_CHECKING:
    from pathlib import Path

logger = structlog.get_logger()


@dataclass
class ExperimentLoader:
    """Manages lightweight experiment scanning using filename-based parsing.

    This class provides fast scanning without loading full records,
    using only filename parsing to extract experiment metadata.

    Attributes:
        directory: Root directory to scan for experiments
        max_workers: Number of parallel workers for I/O operations
        wandb_path: Optional wandb project path for validation
        scanned_experiments: List of valid scanned experiments
        invalid_scanned_experiments: List of experiments that failed wandb validation
        selected_experiment: Currently selected experiment
    """

    _directory: Path | None = None
    max_workers: int = 32
    wandb_path: str | None = None

    # Cached state
    scanned_experiments: list[ScannedExperiment] = field(default_factory=list, init=False)
    invalid_scanned_experiments: list[ScannedExperiment] = field(default_factory=list, init=False)
    selected_experiment: ScannedExperiment | None = field(default=None, init=False)

    @property
    def directory(self) -> Path | None:
        """Get the current directory."""
        return self._directory

    @directory.setter
    def directory(self, path: Path | None) -> None:
        """Set the directory and clear cached scan results."""
        if self._directory != path:
            self._directory = path
            self.scanned_experiments = []
            self.invalid_scanned_experiments = []
            self.selected_experiment = None

    def scan(
        self, *, directory: Path, wandb_path: str | None = None
    ) -> tuple[list[ScannedExperiment], list[ScannedExperiment]]:
        """Perform lightweight scan using filename-based parsing."""
        self.directory = directory

        self.scanned_experiments = []

        self.scanned_experiments = scan_experiments_from_directory(self.directory)
        self.invalid_scanned_experiments = []

        if wandb_path:
            valid, invalid = validate_scanned_experiments_with_wandb(
                self.scanned_experiments, wandb_path=wandb_path
            )
            self.scanned_experiments = valid
            self.invalid_scanned_experiments = invalid

        logger.info(
            "Lightweight scan complete",
            scanned=len(self.scanned_experiments),
            invalid=len(self.invalid_scanned_experiments),
            validated=wandb_path is not None,
        )

        return self.scanned_experiments, self.invalid_scanned_experiments
