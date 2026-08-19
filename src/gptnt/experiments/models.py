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
from pydantic.functional_serializers import field_serializer
from pydantic_ai import ModelMessage, ModelMessagesTypeAdapter, RunUsage
from whenever import Instant

from gptnt.common.logger import monkey_patch_binary_content_repr
from gptnt.common.provenance import Provenance
from gptnt.experiments.db.schema import AsBlob, AsJSON, AsVarchar, DuckDBSchemaMixin
from gptnt.experiments.instance import ExperimentInstance, PlayerContent
from gptnt.ktane.actions import KtaneBaseAction, KtaneGameplayInput
from gptnt.ktane.manuals.definition import ManualBuildDefinition
from gptnt.ktane.mission_spec import KtaneMissionSpec
from gptnt.ktane.state.bomb import BombOutcome, BombState
from gptnt.ktane.state.modules import KtaneModuleId
from gptnt.players.actions import DoNothingAction, PlayerOutputType, SendMessageAction
from gptnt.players.exceptions import AIResponseErrorType
from gptnt.players.observation_handler import Observation
from gptnt.players.specification import (
    CommunicationStyle,
    PlayerCapabilities,
    PlayerProtocol,
    PlayerRole,
)

logger = structlog.get_logger()


ModelMessagesList = Annotated[
    list[ModelMessage],
    Field(default_factory=list),
    PlainSerializer(ModelMessagesTypeAdapter.dump_json, when_used="json"),
    AsBlob,
]


class ExperimentStep(DuckDBSchemaMixin):
    """Record of a single step in the experiment."""

    step: int
    timestamp: float
    """Seconds from the shared experiment start to the beginning of output dispatch."""
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
    list[ExperimentStep],
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

    @property
    def outcome(self) -> BombOutcome | None:
        """Classify the last observed bomb state."""
        for record in reversed(self.step_records):
            if record.bomb_state is not None:
                return record.bomb_state.outcome
        return None

    @property
    def time_remaining(self) -> float | None:
        """Get the time remaining on the bomb at the end of the experiment."""
        for record in reversed(self.step_records):
            if record.bomb_state is not None:
                return record.bomb_state.timer_module.seconds_remaining
        return None

    @property
    def total_modules_solved(self) -> int | None:
        """Get the total number of modules solved by the end of the experiment."""
        for record in reversed(self.step_records):
            if record.bomb_state is not None:
                return sum(1 for module in record.bomb_state.modules if module.is_solved)
        return None

    @property
    def total_strikes(self) -> int | None:
        """Get the total number of strikes by the end of the experiment."""
        for record in reversed(self.step_records):
            if record.bomb_state is not None:
                return record.bomb_state.strike_count
        return None

    @property
    def final_bomb_state(self) -> BombState | None:
        """Get the final bomb state from the step records."""
        for record in reversed(self.step_records):
            if record.bomb_state is not None:
                return record.bomb_state
        return None


class ExperimentPlayerRecord(Provenance, StepRecordsMetricsMixin):
    """Records for a single player in an experiment."""

    experiment_instance: ExperimentInstance
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

        async def _load(record: ExperimentStep) -> None:  # noqa: WPS430
            loaded_record = await record.load_observation()
            loaded_records.append(loaded_record)

        async with anyio.create_task_group() as tg:
            for record in self.step_records:
                tg.start_soon(_load, record)

        sorted_records = sorted(loaded_records, key=attrgetter("timestamp"))
        return self.model_copy(update={"step_records": sorted_records})

    @classmethod
    def from_summary_and_steps(
        cls, summary: "ExperimentSummary", step_records: list[ExperimentStep]
    ) -> Self:
        """Reconstruct a player record from DuckDB-sourced data.

        All `step_records` must belong to the same player (single `player_uuid`).
        """
        if not step_records:
            raise ValueError("Cannot construct ExperimentPlayerRecord with no step records.")

        role = step_records[0].role
        player_content = summary.get_player_content_by_role(role)

        return cls(
            experiment_instance=summary,
            player_content=player_content,
            step_records=step_records,
            is_hard_crash=summary.is_hard_crash,
        )


class ExperimentOutcome(BaseModel):
    """Bomb outcome fields shared by the DuckDB summary and W&B summary."""

    model_config = ConfigDict(frozen=True, populate_by_name=True, from_attributes=True)

    outcome: BombOutcome
    seconds_remaining: Annotated[float, Field(alias="timer_seconds")]
    strike_count: int
    num_modules_solved: int

    @computed_field
    @property
    def is_solved(self) -> bool:
        """Whether the bomb was solved."""
        return self.outcome == BombOutcome.solved

    @computed_field
    @property
    def is_strike_out(self) -> bool:
        """Whether the bomb was strike out."""
        return self.outcome == BombOutcome.strikeout

    @computed_field
    @property
    def is_timed_out(self) -> bool:
        """Whether the bomb was timed out."""
        return self.outcome == BombOutcome.timeout

    @computed_field
    @property
    def is_detonated(self) -> bool:
        """Whether the bomb ended by detonation, including timeout and strikeout."""
        return self.outcome in {BombOutcome.timeout, BombOutcome.strikeout, BombOutcome.detonated}


class ExperimentSummary(ExperimentInstance, Provenance, ExperimentOutcome, DuckDBSchemaMixin):  # noqa: WPS215
    """The recorded result of one experiment execution.

    It combines the experiment instance with its provenance, bomb outcome, and crash state. The
    manual build definition comes from the inherited experiment spec.
    """

    model_config = ConfigDict(populate_by_name=True, frozen=True)

    is_hard_crash: bool

    mission_spec: Annotated[KtaneMissionSpec, AsJSON]
    manual_build: Annotated[ManualBuildDefinition, AsJSON]
    defuser_protocol: Annotated[PlayerProtocol, AsJSON]
    expert_protocol: Annotated[PlayerProtocol | None, AsJSON]
    defuser_capabilities: Annotated[PlayerCapabilities, AsJSON]
    expert_capabilities: Annotated[PlayerCapabilities | None, AsJSON]

    @field_serializer("start_time")
    def serialize_start_time(self, start_time: Instant) -> str:
        """Serialize the instance start time as an ISO-8601 DuckDB value."""
        return str(start_time)

    @computed_field(alias="name")
    @property
    @override
    def attempt_name(self) -> str:
        """Name of this experiment attempt."""
        return super().attempt_name

    @computed_field
    @property
    def seed(self) -> int:
        """Mission seed used by this experiment instance."""
        return self.mission_spec.seed

    @computed_field
    @property
    @override
    def communication_style(self) -> CommunicationStyle:
        """Communication style used by the players."""
        return super().communication_style

    @computed_field
    @property
    def modules(self) -> list[KtaneModuleId]:
        """KTANE modules used by this experiment instance."""
        return self.mission_spec.components

    @computed_field
    @property
    def defuser_capability_fingerprint(self) -> str:
        """Fingerprint of the defuser's capabilities."""
        return self.defuser_capabilities.fingerprint

    @computed_field
    @property
    def expert_capability_fingerprint(self) -> str:
        """Fingerprint of the expert's capabilities, or empty when there is no expert."""
        if self.expert_capabilities is None:
            return ""
        return self.expert_capabilities.fingerprint

    @computed_field
    @property
    def defuser_has_manual(self) -> bool:
        """True when the defuser player was explicitly given the manual."""
        return self.defuser_protocol.include_manual

    @computed_field
    @property
    def mission_key(self) -> str:
        """Identity of this experiment's mission (modules + seed), for grouping/seeding."""
        return self.mission_spec.mission_key

    @property
    def modules_str(self) -> list[str]:
        """Module names for display."""
        return list(self.modules)

    @property
    def is_valid(self) -> bool:
        """Whether this is a valid, completed run, decided by the shared `is_valid_outcome`."""
        return is_valid_outcome(outcome=self.outcome, is_hard_crash=self.is_hard_crash)

    @classmethod
    def from_instance_and_bomb_state(
        cls,
        *,
        instance: ExperimentInstance,
        final_bomb_state: BombState,
        is_hard_crash: bool,
        gptnt_version: str | None = None,
        git_sha: str | None = None,
    ) -> Self:
        """Construct a summary from an experiment instance and its final bomb state."""
        outcome = ExperimentOutcome.model_validate(final_bomb_state)
        # Omit gptnt_version when not supplied so the Provenance default_factory resolves the
        # live version, rather than passing a placeholder the field validator rejects.
        provenance: dict[str, Any] = {"git_sha": git_sha}
        if gptnt_version is not None:
            provenance["gptnt_version"] = gptnt_version

        return cls.model_validate(
            instance.model_dump(exclude_computed_fields=True)
            | outcome.model_dump()
            | {"is_hard_crash": is_hard_crash}
            | provenance
        )


class ExperimentRecord(StepRecordsMetricsMixin):
    """Records for an entire experiment."""

    player_records: list[ExperimentPlayerRecord]

    experiment_instance: ExperimentInstance
    step_records: SortedStepRecords = Field(default_factory=list)
    is_hard_crash: bool

    @classmethod
    def from_player_records(cls, *, player_records: list[ExperimentPlayerRecord]) -> Self:
        """Create an ExperimentRecord from a list of ExperimentPlayerRecords."""
        experiment_instance = player_records[0].experiment_instance
        is_hard_crash = any(player_record.is_hard_crash for player_record in player_records)
        return cls(
            player_records=player_records,
            experiment_instance=experiment_instance,
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


def is_valid_outcome(*, outcome: BombOutcome, is_hard_crash: bool) -> bool:
    """Whether an experiment outcome counts as a valid, completed run.

    Valid means no hard crash and the outcome classified as either solved, timeout, or strikeout.
    This is the single definition shared by the local footer ledger, DuckDB summaries, and W&B
    runs.
    """
    return not is_hard_crash and outcome in {
        BombOutcome.solved,
        BombOutcome.timeout,
        BombOutcome.strikeout,
    }
