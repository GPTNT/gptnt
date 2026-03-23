from dataclasses import asdict
from operator import attrgetter
from pathlib import Path
from typing import Annotated, Any, Self, override

import anyio
import dill
import structlog
from anyio.to_thread import run_sync as run_sync_in_thread
from pydantic import (
    UUID4,
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    ValidationInfo,
    computed_field,
    field_validator,
    model_validator,
)
from pydantic_ai import ModelMessage, ModelMessagesTypeAdapter, RunUsage

from gptnt.common.duckdb import AsBlob, AsJSON, AsVarchar, DuckDBSchemaMixin
from gptnt.common.logger import monkey_patch_binary_content_repr
from gptnt.experiments.experiment_descriptor import ExperimentDescriptor, PlayerContent
from gptnt.experiments.experiments import Condition
from gptnt.ktane.actions import KtaneBaseAction, KtaneGameplayInput
from gptnt.ktane.state.bomb import BombState
from gptnt.ktane.state.modules import KtaneComponent
from gptnt.players.actions import DoNothingAction, PlayerOutputType, SendMessageAction
from gptnt.players.exceptions import AIResponseErrorType
from gptnt.players.observation_handler import Observation
from gptnt.specification import CommunicationStyle, PlayerRole

logger = structlog.get_logger()


ModelMessagesList = Annotated[
    list[ModelMessage],
    Field(default_factory=list),
    PlainSerializer(ModelMessagesTypeAdapter.dump_json, when_used="json"),
    AsBlob,
]


class ExperimentStepRecord(DuckDBSchemaMixin):
    """Record of a single step in the experiment."""

    step: int
    timestamp: float
    role: PlayerRole
    session_id: UUID4
    player_uuid: UUID4
    player_name: str

    output: Annotated[PlayerOutputType | KtaneGameplayInput, AsVarchar]
    raw_output: str | None
    thoughts: str | None = None

    input_messages: ModelMessagesList = Field(default_factory=list)
    new_messages: ModelMessagesList = Field(default_factory=list)

    bomb_state: Annotated[BombState | None, AsJSON]
    observation: Annotated[Observation | Path | None, AsBlob, Field(repr=False)]
    usage: Annotated[RunUsage, AsBlob]
    num_prompt_truncations: int
    error_type: list[AIResponseErrorType] | None = None
    is_reflection: bool = False

    @override
    def __repr__(self) -> str:
        # Monkey-patch BinaryContent's __repr__ to avoid large binary data outputs
        monkey_patch_binary_content_repr()
        return super().__repr__()

    async def load_observation(self) -> Self:
        """Load observation from disk if it's stored as a Path.

        Recreate the model with the loaded observation.
        """
        if isinstance(self.observation, Path):
            async with await anyio.open_file(self.observation, "rb") as obs_file:
                observation_data = await obs_file.read()
                observation = await run_sync_in_thread(dill.loads, observation_data)
                return self.model_copy(update={"observation": observation})
        return self

    @field_validator("input_messages", "new_messages", mode="before")
    @classmethod
    def parse_jsoned_messages(cls, messages: str | list[ModelMessage]) -> list[ModelMessage]:  # noqa: WPS110
        """Custom validator to parse JSON strings back into ModelMessage lists."""
        if not isinstance(messages, str):
            return messages
        return ModelMessagesTypeAdapter.validate_json(messages)

    @model_validator(mode="before")
    @classmethod
    def optionally_skip_heavy_objects(
        cls,
        data: Any,
        info: ValidationInfo,  # noqa: WPS110
    ) -> Any:
        """Optionally skip loading heavy objects based on context."""
        if (
            isinstance(data, dict)
            and isinstance(info.context, dict)
            and info.context.get("skip_heavy_field_loading", False)
        ):
            data["observation"] = None
            data["new_messages"] = []
            data["input_messages"] = []
        return data


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
                for error in record.error_type:
                    error_counts[error] = error_counts.get(error, 0) + 1
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

    @property
    def final_bomb_state(self) -> BombState | None:
        """Get the final bomb state from the step records."""
        for record in reversed(self.step_records):
            if record.bomb_state is not None:
                return record.bomb_state
        return None


class ExperimentPlayerRecord(StepRecordsMetricsMixin):
    """Records for a single player in an experiment."""

    experiment_descriptor: ExperimentDescriptor
    player_content: PlayerContent
    step_records: SortedStepRecords
    is_hard_crash: bool = False

    @property
    def role(self) -> PlayerRole:
        """Get the role of the player in this record."""
        return self.player_content.protocol.role

    async def rebuild_with_observations(self) -> Self:
        """Rebuild the record by loading all observations from disk."""
        loaded_records = []

        async def _load(record: ExperimentStepRecord) -> None:  # noqa: WPS430
            loaded_record = await record.load_observation()
            loaded_records.append(loaded_record)

        async with anyio.create_task_group() as tg:
            for record in self.step_records:
                tg.start_soon(_load, record)

        sorted_records = sorted(loaded_records, key=attrgetter("timestamp"))
        return self.model_copy(update={"step_records": sorted_records})

    @classmethod
    def from_metadata_and_steps(
        cls, metadata: "ExperimentMetadata", step_records: list[ExperimentStepRecord]
    ) -> Self:
        """Reconstruct a player record from DuckDB-sourced data.

        All `step_records` must belong to the same player (single `player_uuid`).
        """
        if not step_records:
            raise ValueError("Cannot construct ExperimentPlayerRecord with no step records.")

        role = step_records[0].role
        player_content = metadata.experiment_descriptor.get_player_content_by_role(role)

        return cls(
            experiment_descriptor=metadata.experiment_descriptor,
            player_content=player_content,
            step_records=step_records,
            is_hard_crash=metadata.is_valid is False,  # ← see note below
        )


class ExperimentMetadata(DuckDBSchemaMixin):
    """Experiment-level metadata — one row per experiment."""

    model_config = ConfigDict(populate_by_name=True)

    attempt_name: Annotated[str, Field(alias="name")]
    session_id: UUID4

    file_paths: list[Path]

    player_uuids: list[UUID4]

    is_valid: bool | None = None

    condition: Condition
    seed: int
    pairing: str
    defuser_name: Annotated[str, Field(alias="defuser")]
    expert_name: Annotated[str | None, Field(alias="expert")]
    communication_style: CommunicationStyle
    attempt: int

    modules: list[KtaneComponent]

    is_solved: bool
    is_detonated: bool
    seconds_remaining: Annotated[float, Field(alias="timer_seconds")]
    strike_count: int
    num_modules_solved: int

    experiment_descriptor: Annotated[ExperimentDescriptor, AsJSON]

    # Any custom tags to describe the experiment
    tags: list[str] = Field(default_factory=list)

    @override
    def __hash__(self) -> int:
        """Hash based on the unique attempt name."""
        return hash((self.attempt_name, self.session_id, tuple(self.player_uuids)))

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
        return self.seconds_remaining <= 0 and not self.is_solved

    @property
    def modules_str(self) -> list[str]:
        """Comma-separated string of module names for easy display."""
        return [module.name for module in self.modules]

    @computed_field
    @property
    def file_names(self) -> list[str]:
        """Compute the list of file names associated with this experiment."""
        return [f"experiment-{self.attempt_name}-{uuid}.json" for uuid in self.player_uuids]


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


def is_valid_experiment(*, is_hard_crash: bool, final_bomb_state: BombState) -> bool:
    """Determine if the experiment is valid (i.e. no hard crashes and good ending)."""
    is_good_solved = (
        final_bomb_state.is_solved is True
        and final_bomb_state.is_timed_out is False
        and final_bomb_state.is_strike_out is False
    )
    is_good_failed = final_bomb_state.is_solved is False and (
        final_bomb_state.is_timed_out is True or final_bomb_state.is_strike_out is True
    )

    return not is_hard_crash and (is_good_solved or is_good_failed)
