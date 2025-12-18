from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from operator import attrgetter
from pathlib import Path
from typing import Annotated, Self

import anyio
import dill
import structlog
from pydantic import UUID4, AfterValidator, BaseModel, Field, computed_field, model_validator
from pydantic_ai import RunUsage
from tqdm import tqdm

from gptnt.ktane.actions import KtaneBaseAction, KtaneGameplayInput
from gptnt.ktane.state.bomb import BombState
from gptnt.players.actions import (
    AIResponseErrorType,
    DoNothingAction,
    PlayerOutputType,
    SendMessageAction,
)
from gptnt.players.observation_handler import Observation
from gptnt.players.specification import PlayerRole
from gptnt.services.experiment_descriptor import ExperimentDescriptor, PlayerContent

logger = structlog.get_logger()


class ExperimentStepRecord(BaseModel):
    """Record of a single step in the experiment."""

    step: int
    timestamp: float
    role: PlayerRole
    session_id: UUID4
    player_uuid: UUID4
    player_name: str

    output: PlayerOutputType | KtaneGameplayInput
    raw_output: str | None
    thoughts: str | None

    bomb_state: BombState | None
    observation: Annotated[Observation | Path | None, Field(repr=False)]
    usage: RunUsage
    error_type: AIResponseErrorType | None = None
    is_reflection: bool = False

    async def load_observation(self) -> Self:
        """Load observation from disk if it's stored as a Path.

        Recreate the model with the loaded observation.
        """
        if isinstance(self.observation, Path):
            async with await anyio.open_file(self.observation, "rb") as obs_file:
                observation_data = await obs_file.read()
                observation = dill.loads(observation_data)  # noqa: S301
                return self.model_copy(update={"observation": observation})
        return self


SortedStepRecords = Annotated[
    list[ExperimentStepRecord],
    AfterValidator(lambda records: sorted(records, key=attrgetter("timestamp"))),
]


class StepRecordsMetricsMixin(BaseModel):
    """Metrics computed from a list of step records."""

    step_records: SortedStepRecords

    @computed_field
    @property
    def num_steps(self) -> int:
        """Compute the number of steps in the experiment."""
        return max((record.step for record in self.step_records), default=0)

    @computed_field
    @property
    def total_usage(self) -> dict[str, int]:
        """Compute the total usage for the experiment."""
        usage = RunUsage()
        for record in self.step_records:  # noqa: WPS519
            usage += record.usage
        return {f"total_{key}": count for key, count in asdict(usage).items()}

    @computed_field
    @property
    def total_game_actions(self) -> int:
        """Count the number of game actions in the experiment."""
        return sum(1 for record in self.step_records if isinstance(record.output, KtaneBaseAction))

    @computed_field
    @property
    def total_messages(self) -> int:
        """Count the number of messages in the experiment."""
        return sum(
            1 for record in self.step_records if isinstance(record.output, SendMessageAction)
        )

    @computed_field
    @property
    def total_do_nothings(self) -> int:
        """Count the number of do-nothing actions in the experiment."""
        return sum(1 for record in self.step_records if isinstance(record.output, DoNothingAction))

    @computed_field
    @property
    def total_errors(self) -> dict[AIResponseErrorType, int]:
        """Count the number of errors by type in the experiment."""
        error_counts: dict[AIResponseErrorType, int] = {}
        for record in self.step_records:
            if record.error_type is not None:
                error_counts[record.error_type] = error_counts.get(record.error_type, 0) + 1
        return error_counts

    @computed_field
    @property
    def is_solved(self) -> bool | None:
        """Check if the bomb was solved in the experiment."""
        for record in reversed(self.step_records):
            if record.bomb_state is not None:
                return record.bomb_state.is_solved
        return None

    @computed_field
    @property
    def is_strike_out(self) -> bool | None:
        """Check if the bomb was strike out in the experiment."""
        for record in reversed(self.step_records):
            if record.bomb_state is not None:
                return record.bomb_state.is_strike_out
        return None

    @computed_field
    @property
    def is_timed_out(self) -> bool | None:
        """Check if the bomb was timed out in the experiment."""
        for record in reversed(self.step_records):
            if record.bomb_state is not None:
                return record.bomb_state.is_timed_out
        return None

    @computed_field
    @property
    def time_remaining(self) -> float | None:
        """Get the time remaining on the bomb at the end of the experiment."""
        for record in reversed(self.step_records):
            if record.bomb_state is not None:
                return record.bomb_state.timer_module.seconds_remaining
        return None

    @computed_field
    @property
    def total_modules_solved(self) -> int | None:
        """Get the total number of modules solved by the end of the experiment."""
        for record in reversed(self.step_records):
            if record.bomb_state is not None:
                return sum(1 for module in record.bomb_state.modules if module.is_solved)
        return None

    @computed_field
    @property
    def total_strikes(self) -> int | None:
        """Get the total number of strikes by the end of the experiment."""
        for record in reversed(self.step_records):
            if record.bomb_state is not None:
                return record.bomb_state.current_strikes
        return None


class ExperimentPlayerRecord(StepRecordsMetricsMixin):
    """Records for a single player in an experiment."""

    experiment_descriptor: ExperimentDescriptor
    player_content: PlayerContent
    step_records: SortedStepRecords
    is_hard_crash: bool = False

    async def rebuild_with_observations(self) -> Self:
        """Rebuild the record by loading all observations from disk."""
        loaded_records = []
        for record in self.step_records:
            loaded_record = await record.load_observation()  # noqa: WPS476
            loaded_records.append(loaded_record)
        return self.model_copy(update={"step_records": loaded_records})


class ExperimentRecord(StepRecordsMetricsMixin):
    """Records for an entire experiment."""

    player_records: list[ExperimentPlayerRecord]

    experiment_descriptor: ExperimentDescriptor
    step_records: SortedStepRecords = Field(default_factory=list)
    is_hard_crash: bool

    @classmethod
    def from_player_records(cls, *, player_records: list[ExperimentPlayerRecord]) -> Self:
        """Create an ExperimentRecord from a list of ExperimentPlayerRecords."""
        experiment_descriptor = player_records[0].experiment_descriptor
        is_hard_crash = any(player_record.is_hard_crash for player_record in player_records)
        return cls(
            player_records=player_records,
            experiment_descriptor=experiment_descriptor,
            is_hard_crash=is_hard_crash,
        )

    @model_validator(mode="after")
    def aggregate_step_records(self) -> Self:
        """Get all step records from all players."""
        all_step_records = []
        for player_record in self.player_records:
            all_step_records.extend(player_record.step_records)
        self.step_records = sorted(all_step_records, key=attrgetter("timestamp"))
        return self


def build_experiment_records_from_player_records(
    *, player_records: list[ExperimentPlayerRecord]
) -> list[ExperimentRecord]:
    """Collate all the player records together into experiment records."""
    experiment_dict: dict[UUID4, list[ExperimentPlayerRecord]] = defaultdict(list)
    for player_record in player_records:
        exp_id = player_record.experiment_descriptor.session_id
        experiment_dict[exp_id].append(player_record)

    experiment_records = [
        ExperimentRecord.from_player_records(player_records=exp_player_records)
        for exp_player_records in experiment_dict.values()
    ]

    return experiment_records


def _load_player_record(file_path: Path) -> ExperimentPlayerRecord:
    """Load a single player record from disk."""
    return ExperimentPlayerRecord.model_validate_json(file_path.read_text())


def load_player_records_from_dir(
    path: Path, *, max_workers: int = 32
) -> list[ExperimentPlayerRecord]:
    """Load all player records as fast as possible.

    Uses multithreading for this.
    """
    all_files = list(path.rglob("experiment-*.json"))

    logger.info("Loading player records", num_files=len(all_files), max_workers=max_workers)

    player_records: list[ExperimentPlayerRecord] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_path = {
            executor.submit(_load_player_record, file_path): file_path for file_path in all_files
        }
        for future in tqdm(
            as_completed(future_to_path), total=len(future_to_path), desc="Loading player records"
        ):
            player_record = future.result()
            player_records.append(player_record)

    return player_records
