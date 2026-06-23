from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import anyio
import dill
import logfire
import orjson
import structlog
from whenever import Instant

from gptnt.common.paths import Paths
from gptnt.experiments.models import ExperimentPlayerRecord, ExperimentStepRecord
from gptnt.experiments.provenance import git_sha, gptnt_edition, gptnt_version
from gptnt.players.observation_handler import Observation

if TYPE_CHECKING:
    from pathlib import Path

    from pydantic import UUID4
    from pydantic_ai import ModelMessage

    from gptnt.common.image_ops import PNGBytes
    from gptnt.experiments.descriptor import ExperimentDescriptor
    from gptnt.ktane.actions import KtaneGameplayInput
    from gptnt.ktane.state.bomb import BombState
    from gptnt.players.actions import PlayerOutputType
    from gptnt.players.result import AgentCallResult
    from gptnt.specification import PlayerCapabilities, PlayerProtocol

logger = structlog.get_logger()


@dataclass(kw_only=True)
class ExperimentPlayerRecorder:
    """Record the events of an experiment for a single player."""

    capabilities: PlayerCapabilities
    player_uuid: UUID4 = field(init=False, repr=False)

    experiment_descriptor: ExperimentDescriptor | None = field(default=None, init=False)
    protocol: PlayerProtocol | None = field(default=None, init=False)

    start_time: Instant = field(init=False, repr=False)

    step_records: list[ExperimentStepRecord] = field(default_factory=list, init=False)
    num_steps: int = field(default=0, init=False)

    output_dir: Path = field(init=False, repr=False, default=Paths().experiment_outputs)
    observations_dir: Path = field(init=False, repr=False, default=Paths().output_observations)

    # Buffer for the current step's context (stored before agent responds)
    last_output: AgentCallResult[PlayerOutputType | KtaneGameplayInput] | None = field(
        default=None, init=False
    )
    _current_bomb_state: BombState | None = field(default=None, init=False)
    _current_observation_path: Path | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        """Initialize the class."""
        self.observations_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def configure_for_experiment(
        self,
        *,
        experiment_descriptor: ExperimentDescriptor,
        protocol: PlayerProtocol,
        player_uuid: UUID4,
    ) -> None:
        """Start tracking an experiment."""
        self.experiment_descriptor = experiment_descriptor
        self.protocol = protocol
        self.player_uuid = player_uuid
        self.start_time = Instant.now()
        logger.debug(
            "Configured experiment logger",
            attempt_name=experiment_descriptor.name,
            protocol=protocol,
            player_uuid=str(player_uuid),
        )

    async def store_step_context(
        self,
        *,
        bomb_state: BombState,
        frames: list[PNGBytes],
        segm_mask: PNGBytes | None,
        som_image: PNGBytes,
    ) -> None:
        """Store the observation and bomb state context for the current step.

        This is called during input building, before the agent responds.
        """
        self._current_bomb_state = bomb_state

        observation = Observation(frames=frames, segm_mask=segm_mask, som_image=som_image)

        # Save observation to disk
        obs_path = self.observations_dir / f"{self.player_uuid}_{Instant.now().format_iso()}.pkl"
        async with await anyio.open_file(obs_path, "wb") as obs_file:
            _ = await obs_file.write(dill.dumps(observation))

        self._current_observation_path = obs_path

    def track_step(
        self,
        *,
        agent_call_result: AgentCallResult[PlayerOutputType | KtaneGameplayInput],
        num_prompt_truncations: int,
        input_messages: list[ModelMessage],
        is_reflection: bool = False,
    ) -> None:
        """Record a complete step by combining all buffered context.

        This is called after the agent responds and output has been stored. Combines buffered
        bomb_state, observation_path, and output into one record.
        """
        assert self.experiment_descriptor is not None, "Must configure experiment before tracking"
        assert self.protocol is not None, "Must configure experiment before tracking"

        self.num_steps += 1

        record = ExperimentStepRecord(
            timestamp=self._seconds_since_start,
            role=self.protocol.role,
            session_id=self.experiment_descriptor.session_id,
            player_uuid=self.player_uuid,
            player_name=self.capabilities.player_name,
            step=self.num_steps,
            output=agent_call_result.output,
            raw_output=agent_call_result.raw_output,
            thoughts=agent_call_result.thoughts,
            bomb_state=self._current_bomb_state,
            observation=self._current_observation_path,
            usage=agent_call_result.usage,
            error_type=agent_call_result.ai_response_error,
            is_reflection=is_reflection,
            num_prompt_truncations=num_prompt_truncations,
            input_messages=input_messages,
            new_messages=agent_call_result.new_messages,
        )

        self.last_output = agent_call_result
        self.step_records.append(record)

        # Clear all buffers for next step
        self._current_bomb_state = None
        self._current_observation_path = None

        logger.debug(
            "Tracked step",
            step=self.num_steps,
            command_type=type(agent_call_result.output).__name__,
            is_reflection=is_reflection,
        )

    def reset(self) -> None:
        """Reset all tracking state for a new episode."""
        self.step_records.clear()
        self.num_steps = 0
        self._current_bomb_state = None
        self._current_observation_path = None
        self.last_output = None

    @logfire.instrument("Stop experiment tracker")
    async def on_experiment_stop(self, *, is_hard_crash: bool = False) -> None:
        """Finish tracking and load all observations into step records."""
        player_record = self.build_player_record(is_hard_crash=is_hard_crash)
        await self.save_player_record_to_disk(player_record=player_record)

    def build_player_record(self, *, is_hard_crash: bool = False) -> ExperimentPlayerRecord:
        """Build the ExperimentPlayerRecord from the current state."""
        assert self.experiment_descriptor is not None, "Must configure experiment before building"
        assert self.protocol is not None, "Must configure experiment before building"
        player_content = self.experiment_descriptor.get_player_content_by_role(
            role=self.protocol.role
        )
        return ExperimentPlayerRecord(
            experiment_descriptor=self.experiment_descriptor,
            player_content=player_content,
            step_records=self.step_records,
            is_hard_crash=is_hard_crash,
            gptnt_version=gptnt_version(),
            gptnt_edition=gptnt_edition(),
            git_sha=git_sha(),
        )

    async def save_player_record_to_disk(self, *, player_record: ExperimentPlayerRecord) -> None:
        """Save the given player record to disk."""
        if not player_record.step_records:
            logger.warning(
                "No step records to save for player record, skipping disk write.",
                player_uuid=str(player_record.player_content.uuid),
            )
            return

        player_record = await player_record.rebuild_with_observations()

        output_path = anyio.Path(
            self.output_dir.joinpath(
                f"experiment-{player_record.experiment_descriptor.name}-{player_record.player_content.uuid}.json"
            )
        )
        # Make sure the folder exists and file is created before
        self.output_dir.mkdir(parents=True, exist_ok=True)
        await output_path.touch(exist_ok=True)

        output_data = orjson.dumps(player_record.model_dump(mode="json"))
        _ = await output_path.write_bytes(output_data)

    def add_final_bomb_state(self, *, final_bomb_state: BombState) -> None:
        """Add the final bomb state to the last step record."""
        if self.step_records:
            self.step_records[-1] = self.step_records[-1].model_copy(
                update={"bomb_state": final_bomb_state}
            )

    @property
    def _seconds_since_start(self) -> float:
        """Get the time delta since the start of the experiment in seconds."""
        return (Instant.now() - self.start_time).in_seconds()
