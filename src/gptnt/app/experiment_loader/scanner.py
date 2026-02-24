"""Lightweight experiment scanner with filename-based parsing and wandb validation.

This module scans a directory for experiment files, parses experiment names from filenames,
optionally validates against wandb, and returns lightweight ScannedExperiment objects.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, get_args

from pydantic_core import from_json

from gptnt.experiments.experiments import Condition
from gptnt.experiments.wandb import (
    collate_runs_per_experiment_per_game,
    get_invalid_runs_from_collated_runs,
    get_runs_from_wandb,
)
from gptnt.ktane.state.bomb import BombState
from gptnt.players.specification import CommunicationStyle

if TYPE_CHECKING:
    from pathlib import Path

# Regex for parsing experiment filenames: experiment-{experiment_name}-{player_uuid}.json
_FILENAME_PATTERN = re.compile(r"^experiment-(.+)-([a-f0-9-]+)\.json$")

# Regex for stripping session UUID from experiment name
# Format: {config}_({pairing})-{session_uuid}
# The session UUID is the last UUID-like pattern after the closing parenthesis
_SESSION_UUID_PATTERN = re.compile(r"-([a-f0-9-]+)$")


def _strip_session_uuid(experiment_name: str) -> str:
    """Strip the session UUID from the experiment name for de-duplication.

    Experiment names include a session UUID at the end:
    e.g., single_module_sync_Simon_286_(defuser=qwen3vl--expert=internvl35)-2362252e-3648-4f94-a33f

    For de-duplication, we want to group by the config without the session UUID:
    e.g., single_module_sync_Simon_286_(defuser=qwen3vl--expert=internvl35)
    """
    # Find the last UUID pattern after the closing parenthesis
    match = _SESSION_UUID_PATTERN.search(experiment_name)
    if match and ")" in experiment_name:
        # Make sure the UUID is after the closing parenthesis
        paren_pos = experiment_name.rfind(")")
        uuid_pos = match.start()
        if uuid_pos > paren_pos:
            # Strip the UUID by removing everything from the last hyphen before it
            return experiment_name[:uuid_pos]
    return experiment_name


@dataclass
class ScannedExperiment:
    """Lightweight experiment metadata parsed from filename.

    The experiment_name is the base configuration without session UUID, ensuring proper de-
    duplication. Multiple runs of the same experiment (with different session UUIDs) are grouped
    together.

    The experiment_name is parsed on-demand via properties to extract structured information.
    """

    experiment_name: str  # Base name without session UUID
    file_paths: list[Path]  # May include files from multiple sessions
    total_size_bytes: int
    bomb_state: BombState

    @property
    def condition(self) -> str:
        """Extract condition from experiment name.

        Format: {condition}_{communication_style}_{modules}_{seed}_({pairing})
        """
        for condition in get_args(Condition.__value__):
            if self.experiment_name.startswith(condition):
                return condition
        raise ValueError(f"Condition not found in experiment name: {self.experiment_name}")

    @property
    def communication_style(self) -> str:
        """Extract communication style from experiment name."""
        for communication_style in get_args(CommunicationStyle.__value__):
            if f"_{communication_style}_" in self.experiment_name:
                return communication_style
        raise ValueError(
            f"Communication style not found in experiment name: {self.experiment_name}"
        )

    @property
    def modules(self) -> list[str]:
        """Extract sorted module names."""
        names = sorted(module.name.value for module in self.bomb_state.modules)
        return names

    @property
    def seed(self) -> int:
        """Extract seed from experiment name."""
        # Seed is the second-to-last underscore-separated part
        parts = self.experiment_name.split("_")
        if len(parts) < 3:  # noqa: PLR2004
            return 0
        try:
            # The seed is before the pairing (which is in parentheses)
            # So it's at index -2
            return int(parts[-2])
        except (ValueError, IndexError):
            return 0

    @property
    def pairing(self) -> str:
        """Extract pairing from experiment name.

        Pairing is the last part in format: (defuser=name--expert=name)
        """
        # Find the part in parentheses at the end
        if "(" in self.experiment_name and ")" in self.experiment_name:
            start = self.experiment_name.rfind("(")
            end = self.experiment_name.rfind(")")
            return self.experiment_name[start + 1 : end]
        return ""

    @property
    def defuser(self) -> str:
        """Extract defuser name from pairing."""
        assert "defuser=" in self.pairing
        parts = self.pairing.split("--")
        for part in parts:
            if part.startswith("defuser="):
                return part.split("=", 1)[1].split("+")[0]
        raise ValueError(f"Defuser not found in pairing: {self.pairing}")

    @property
    def expert(self) -> str:
        """Extract expert name from pairing."""
        if "expert=" in self.pairing:
            parts = self.pairing.split("--")
            for part in parts:
                if part.startswith("expert="):
                    return part.split("=", 1)[1]
        raise ValueError(f"Expert not found in pairing: {self.pairing}")


def _parse_filename(path: Path) -> tuple[str, str] | None:
    """Parse experiment filename to extract experiment name and player UUID."""
    match = _FILENAME_PATTERN.match(path.name)
    if not match:
        return None
    return match.group(1), match.group(2)


def _group_by_session(file_paths: list[Path]) -> dict[str, list[Path]]:
    """Group experiment files by base experiment config (without session UUID).

    Files from different experiment sessions (different UUIDs) but the same
    configuration should be grouped together for de-duplication.

    Args:
        file_paths: List of experiment file paths

    Returns:
        Mapping of base_experiment_name → list of file paths
    """
    grouped: dict[str, list[Path]] = {}

    for path in file_paths:
        parsed = _parse_filename(path)
        if not parsed:
            continue

        experiment_name, _ = parsed
        # Strip session UUID to group by base config
        base_name = _strip_session_uuid(experiment_name)

        if base_name not in grouped:
            grouped[base_name] = []
        grouped[base_name].append(path)

    return grouped


def scan_experiments_from_directory(directory: Path) -> list[ScannedExperiment]:
    """Scan directory for experiment files with de-duplication by base config.

    This performs a lightweight scan by only reading filenames and file sizes,
    not file contents. Experiments with the same configuration but different
    session UUIDs are grouped together as a single experiment.

    Args:
        directory: Directory to scan for experiment files

    Returns:
        List of ScannedExperiment objects (de-duplicated by base config)
    """
    # Find all experiment files
    experiment_files = list(directory.rglob("experiment-*.json"))

    if not experiment_files:
        return []

    # Group files by base config (strips session UUID for de-duplication)
    grouped = _group_by_session(experiment_files)

    # Create ScannedExperiment objects
    scanned_experiments: list[ScannedExperiment] = []
    for base_name, file_paths in grouped.items():
        total_size = sum(path.stat().st_size for path in file_paths)
        bomb_states = (grab_last_bomb_state_from_experiment_file(path) for path in file_paths)
        bomb_state = next((state for state in bomb_states if state is not None), None)
        assert bomb_state is not None, (
            f"Could not extract bomb state from any files for experiment: {base_name}"
        )

        scanned_experiments.append(
            ScannedExperiment(
                experiment_name=base_name,  # Base name without session UUID
                file_paths=file_paths,
                bomb_state=bomb_state,
                total_size_bytes=total_size,
            )
        )
    return scanned_experiments


def grab_last_bomb_state_from_experiment_file(file_path: Path) -> BombState | None:
    """Grab the last bomb state from an experiment file without fully loading it.

    This is a lightweight way to get the final bomb state for filtering or summary purposes without
    parsing the entire experiment.
    """
    player_records = from_json(file_path.read_bytes())
    last_step = player_records["step_records"][-1]
    if last_step["bomb_state"] is not None:
        return BombState.model_validate(last_step["bomb_state"])
    return None


def validate_scanned_experiments_with_wandb(
    scanned_experiments: list[ScannedExperiment], wandb_path: str
) -> tuple[list[ScannedExperiment], list[ScannedExperiment]]:
    """Validate scanned experiments against wandb and filter out invalid ones.

    This ensures proper de-duplication: scanned_experiments are already grouped
    by base config (without session UUID), so each unique experiment configuration
    appears only once. The validation checks wandb using these base names.

    Args:
        scanned_experiments: List of scanned experiments (already de-duplicated by base config)
        wandb_path: Path to wandb project in format "entity/project"

    Returns:
        Tuple of (valid_experiments, invalid_experiments)
        - valid_experiments: Experiments with valid wandb runs
        - invalid_experiments: Experiments with invalid or no wandb runs
    """
    all_names = {exp.experiment_name for exp in scanned_experiments}

    # Get runs from wandb filtered by experiment names
    wandb_runs = get_runs_from_wandb(
        wandb_path,
        additional_filters=[{"$or": [{"config.experiment_name": name} for name in all_names]}],
    )

    # If no runs found, all experiments are invalid (not yet run)
    if not wandb_runs:
        return [], scanned_experiments

    # Collate and find invalid runs
    # Note: There may be multiple runs per experiment (multiple games)
    runs_per_experiment_per_game = collate_runs_per_experiment_per_game(wandb_runs)
    invalid_runs = get_invalid_runs_from_collated_runs(runs_per_experiment_per_game)

    # Build set of invalid experiment names (from invalid runs)
    invalid_experiment_names = {run.config["experiment_name"] for run in invalid_runs}

    # Build set of all experiment names that have any wandb runs
    all_wandb_experiment_names = {run.config["experiment_name"] for run in wandb_runs}

    # Valid experiments are those with wandb runs that are NOT in the invalid set
    valid_experiment_names = all_wandb_experiment_names - invalid_experiment_names

    # De-duplicate by experiment_name: filter scanned experiments based on valid names
    # Each experiment appears only once in scanned_experiments (already grouped by name)
    valid_experiments = [
        exp for exp in scanned_experiments if exp.experiment_name in valid_experiment_names
    ]
    invalid_experiments = [
        exp for exp in scanned_experiments if exp.experiment_name not in valid_experiment_names
    ]

    return valid_experiments, invalid_experiments
