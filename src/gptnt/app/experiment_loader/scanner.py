from collections import defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Literal, Self, get_args, override

import structlog
from sqlalchemy import Column, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlmodel import Field, SQLModel

from gptnt.app.experiment_loader._bomb_state import grab_last_bomb_state_from_experiment_file
from gptnt.experiments.experiments import Condition
from gptnt.players.specification import CommunicationStyle

logger = structlog.get_logger()


def _extract_player_uuid(experiment_name: str, *, uuid_length: int = 36) -> str:
    """Extract the player UUID from the experiment name.

    Experiment names include a player UUID at the end:
    e.g., single_module_sync_Simon_286_(defuser=qwen3vl--expert=internvl35)-2362252e-3648-4f94-a33f
    """
    return experiment_name[-uuid_length:]


def _parse_condition(experiment_name: str) -> Condition:
    """Return the experiment condition prefix, or None if not recognised."""
    for condition in get_args(Condition.__value__):
        if condition in experiment_name:
            return condition
    raise ValueError(f"Unrecognised condition in experiment name: {experiment_name}")


def _parse_communication_style(experiment_name: str) -> CommunicationStyle:
    """Return the communication style token, or None if not found."""
    for style in get_args(CommunicationStyle.__value__):
        if f"_{style}_" in experiment_name:
            return style
    raise ValueError(f"Unrecognised communication style in experiment name: {experiment_name}")


def _parse_seed(experiment_name: str) -> int:
    """Extract the integer seed from the experiment name."""
    parts = experiment_name.split("_")
    if len(parts) < 3:  # noqa: PLR2004
        return 0
    try:
        return int(parts[-2])
    except (ValueError, IndexError) as err:
        raise ValueError(f"Could not parse seed from experiment name: {experiment_name}") from err


def _parse_pairing(experiment_name: str) -> str:
    """Extract the pairing string ``defuser=X--expert=Y`` from the name."""
    if "(" in experiment_name and ")" in experiment_name:
        start = experiment_name.rfind("(")
        end = experiment_name.rfind(")")
        return experiment_name[start + 1 : end]
    raise ValueError(f"Could not parse pairing from experiment name: {experiment_name}")


def _parse_defuser(pairing: str) -> str:
    """Extract the defuser model name from a pairing string."""
    for part in pairing.split("--"):
        if part.startswith("defuser="):
            return part.split("=", 1)[1].split("+")[0]
    raise ValueError(f"Could not parse defuser from pairing string: {pairing}")


def _parse_expert(pairing: str) -> str:
    """Extract the expert model name from a pairing string."""
    for part in pairing.split("--"):
        if part.startswith("expert="):
            return part.split("=", 1)[1]
    raise ValueError(f"Could not parse expert from pairing string: {pairing}")


class ScannedExperiment(SQLModel, table=True):
    """Experiment metadata — both the DuckDB ORM table and the in-memory UI object.

    All fields are populated at import time by :func:`_process_group`.
    Computed fields (``condition``, ``seed``, ``pairing``, etc.) that were
    previously ``@property`` methods are stored directly so they can be queried
    from DuckDB without loading the full record.

    List fields use PostgreSQL ``ARRAY(Text)`` via duckdb-engine's inherited
    dialect.  They are nullable in the DB (``list[str] | None``) so SQLAlchemy
    does not raise on a missing value; call ``exp.modules or []`` at use-sites.
    """

    __table_args__ = {"extend_existing": True}
    experiment_name: str = Field(primary_key=True)

    # Stored as TEXT[] — Python attr name differs from DB column so the
    # ``file_paths`` property can provide ``list[Path]`` without conflict.
    file_path_strings: list[str] | None = Field(
        default=None, sa_column=Column("file_paths", ARRAY(Text), nullable=True)
    )
    player_uuids: list[str] | None = Field(
        default=None, sa_column=Column(ARRAY(Text), nullable=True)
    )

    total_size_bytes: int = 0

    modules: list[str] | None = Field(default=None, sa_column=Column(ARRAY(Text), nullable=True))

    is_solved: bool
    is_detonated: bool
    timer_seconds: float = 0
    strike_count: int = 0
    num_modules_solved: int = 0

    # Stored computed fields (derived from experiment_name at scan/import time)
    condition: str
    seed: int
    pairing: str
    defuser: str
    expert: str
    communication_style: str

    is_wandb_valid: bool | None = Field(default=None)

    tags: list[str] | None = Field(default=None, sa_column=Column(ARRAY(Text), nullable=True))

    @override
    def __hash__(self) -> int:
        file_path_strings_for_hash = (
            tuple(self.file_path_strings) if self.file_path_strings else ()
        )
        player_uuids_for_hash = tuple(self.player_uuids) if self.player_uuids else ()
        return hash(
            (
                self.experiment_name,
                file_path_strings_for_hash,
                player_uuids_for_hash,
                self.total_size_bytes,
            )
        )

    @property
    def file_paths(self) -> list[Path]:
        """Convenience property returning file paths as Path objects."""
        return [Path(fp) for fp in (self.file_path_strings or [])]

    @property
    def defuser_has_manual(self) -> bool:
        """True when the defuser player was given the physical manual."""
        return "+manual" in (self.pairing or "")

    @property
    def is_strike_out(self) -> bool:
        """True if the experiment ended with a strikeout (3 strikes and detonation)."""
        return self.strike_count > 2 and not self.is_solved  # noqa: PLR2004

    @property
    def is_timeout(self) -> bool:
        """True if the experiment ended with a timeout (0 seconds remaining and not solved)."""
        return self.timer_seconds <= 0 and not self.is_solved

    @property
    def end_state(self) -> Literal["Solved", "Strike Out", "Timeout", "Unknown"]:
        """Return the experiment end state as a human-readable string."""
        if self.is_solved:
            return "Solved"
        if self.is_strike_out:
            return "Strike Out"
        if self.is_timeout:
            return "Timeout"
        return "Unknown"

    @classmethod
    def from_files(cls, experiment_name: str, file_paths: list[Path]) -> Self:
        """Factory method to create a ScannedExperiment from a list of file paths."""
        experiment_name = experiment_name.replace("experiment-", "").strip()
        total_size = sum(path.stat().st_size for path in file_paths)
        loaded_bomb_state_generator = (
            grab_last_bomb_state_from_experiment_file(path) for path in file_paths
        )
        bomb_state = next(
            (state for state in loaded_bomb_state_generator if state is not None), None
        )

        if bomb_state is None:
            raise ValueError(
                f"Could not extract bomb state from any files for experiment {experiment_name}"
            )
        pairing = _parse_pairing(experiment_name)
        strike_count = len(bomb_state.strikes) if bomb_state.strikes else 0

        return cls(
            experiment_name=experiment_name,
            file_path_strings=[str(fp) for fp in file_paths],
            total_size_bytes=total_size,
            player_uuids=[_extract_player_uuid(path.stem) for path in file_paths],
            modules=sorted(module.name.value for module in bomb_state.modules),
            is_solved=bomb_state.is_solved,
            is_detonated=bomb_state.is_detonated,
            timer_seconds=bomb_state.timer_module.seconds_remaining,
            strike_count=strike_count,
            condition=_parse_condition(experiment_name),
            seed=_parse_seed(experiment_name),
            pairing=pairing,
            defuser=_parse_defuser(pairing),
            expert=_parse_expert(pairing),
            communication_style=_parse_communication_style(experiment_name),
            num_modules_solved=bomb_state.num_modules_solved,
        )


def _group_by_experiment(
    file_paths: list[Path], *, uuid_length: int = 36
) -> dict[str, list[Path]]:
    """Group experiment files by base experiment config (without player UUID).

    Files from different experiment players (different UUIDs) but the same configuration should be
    grouped together for de-duplication.
    """
    grouped = defaultdict(list)
    for path in file_paths:
        # Remove trailing -{uuid}
        experiment_name = path.stem[: -(uuid_length + 1)]
        grouped[experiment_name].append(path)

    return grouped


def scan_experiments_from_directory(  # noqa: WPS210
    directory: Path, on_progress: Callable[[int, int], None] | None = None, max_workers: int = 32
) -> tuple[list[ScannedExperiment], list[Path]]:
    """Scan directory for experiment files with de-duplication by base config.

    This performs a lightweight scan by only reading filenames and file sizes, not file contents.
    Experiments with the same configuration but different session UUIDs are grouped together as a
    single experiment.

    Args:
        directory: Directory to scan for experiment files
        files_to_skip: Optional set of file names to skip during scanning
        on_progress: Optional callback invoked after each group is processed.
            Receives `(processed, total)`.
        max_workers: Number of threads for parallel file I/O.

    Returns:
        Tuple of (scanned_experiments, unparsable_files) where unparsable_files contains paths to
        files that could not be parsed as valid experiment JSON.
    """
    # Find all experiment files
    experiment_files = list(directory.rglob("experiment-*.json"))
    if not experiment_files:
        return [], []

    # Group files by base config (strips player UUID for de-duplication)
    grouped = _group_by_experiment(experiment_files)
    if on_progress is not None:
        on_progress(0, len(grouped))

    scanned_experiments: list[ScannedExperiment] = []
    unparsable_files: list[Path] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(ScannedExperiment.from_files, base_name, file_paths): (
                base_name,
                file_paths,
            )
            for base_name, file_paths in grouped.items()
        }
        for idx, future in enumerate(as_completed(futures)):
            parse_result = future.result()

            if parse_result:
                scanned_experiments.append(parse_result)
            else:
                base_name, file_paths = futures[future]
                logger.warning(
                    "Could not extract bomb state from any files for experiment, skipping",
                    experiment=base_name,
                    files=file_paths,
                )
                unparsable_files.extend(file_paths)

            if on_progress is not None:
                on_progress(idx + 1, len(grouped))

    return scanned_experiments, unparsable_files
