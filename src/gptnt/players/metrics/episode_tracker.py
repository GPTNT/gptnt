import io
import itertools
from contextlib import suppress
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from functools import partial
from pathlib import Path
from typing import Any

import anyio
import dill
import logfire
import polars as pl
import wandb
import weave
from anyio.to_thread import run_sync as run_sync_in_thread
from PIL import Image
from pydantic import UUID4, BaseModel, TypeAdapter
from pydantic_ai import RunUsage
from pydantic_ai.messages import ModelMessage
from structlog import get_logger
from tqdm import tqdm
from weave.trace.weave_client import WeaveClient
from whenever import Instant

from gptnt.common.paths import Paths
from gptnt.ktane.state.bomb import BombState
from gptnt.players.actions import (
    DoNothingAction,
    DoNothingActionWithThoughts,
    InteractGameActionType,
    PlayerOutputType,
    SendMessageAction,
    SendMessageActionWithThoughts,
)
from gptnt.players.ai.message_history import AgentMessageInput
from gptnt.players.metrics.structures import (
    ActionMetric,
    AIResponseErrorType,
    BombStateMetric,
    DoNothingMetric,
    MessageMetric,
    ObservationMetric,
)
from gptnt.players.specification import PlayerCapabilities, PlayerProtocol, PlayerRole
from gptnt.services.experiment_descriptor import ExperimentDescriptor

_logger = get_logger()


@dataclass(kw_only=True)
class EpisodeTracker:  # noqa: WPS214
    """Tracks metrics for an episode."""

    wandb_entity: str
    wandb_project: str

    wandb_init_kwargs: dict[str, Any] = field(default_factory=dict)
    """Keyword arguments for initializing WandB."""

    weave_client: WeaveClient = field(init=False, repr=False)
    """Weave client for tracing."""
    _weave_call: Any | None = field(default=None, init=False, repr=False)

    capabilities: PlayerCapabilities
    """Metadata about the player.

    This is constant for the player so it can be given up front.
    """
    player_uuid: UUID4 = field(init=False, repr=False)

    experiment_descriptor: ExperimentDescriptor | None = field(default=None, init=False)
    protocol: PlayerProtocol | None = field(default=None, init=False)

    start_time: Instant = field(init=False, repr=False)

    # Counters
    num_requests: int = field(default=0, init=False)
    num_invalid_locations: int = field(default=0, init=False)
    """Number of invalid SoM locations."""
    num_prompt_truncations: int = field(default=0, init=False)
    """Number of prompt truncations (because it got too long)."""

    error_event_per_request: list[AIResponseErrorType | None] = field(
        default_factory=list, init=False
    )

    actions: list[ActionMetric] = field(default_factory=list, init=False)
    messages_sent: list[MessageMetric] = field(default_factory=list, init=False)
    do_nothing_actions: list[DoNothingMetric] = field(default_factory=list, init=False)
    bomb_states: list[BombStateMetric] = field(default_factory=list, init=False)
    reflections: list[MessageMetric] = field(default_factory=list, init=False)
    observation_files: list[Path] = field(default_factory=list, init=False)
    """List of observations taken during the episode."""

    usages: list[RunUsage] = field(default_factory=list, init=False)

    _max_sequential_errors: int = 5

    _observations_dir: Path = field(init=False, repr=False, default=Paths().output_observations)

    def __post_init__(self) -> None:
        """Initialize the Weave client and WandB."""
        self.weave_client = weave.init(project_name=f"{self.wandb_entity}/{self.wandb_project}")
        self._observations_dir.mkdir(parents=True, exist_ok=True)
        _logger.info(f"saving obs to {self._observations_dir}")

    @property
    def num_server_errors(self) -> int:
        """Get the total number of server errors."""
        return sum(
            error == AIResponseErrorType.server_error for error in self.error_event_per_request
        )

    @property
    def sequential_server_errors(self) -> int:
        """Get the number of sequential server errors."""
        reversed_errors = (
            error == AIResponseErrorType.server_error
            for error in reversed(self.error_event_per_request)
        )
        return sum(itertools.takewhile(bool, reversed_errors))

    @property
    def num_invalid_formats(self) -> int:
        """Get the total number of invalid formats."""
        return sum(
            error == AIResponseErrorType.invalid_format for error in self.error_event_per_request
        )

    @property
    def sequential_invalid_formats(self) -> int:
        """Get the number of sequential invalid formats."""
        reversed_errors = (
            error == AIResponseErrorType.invalid_format
            for error in reversed(self.error_event_per_request)
        )
        return sum(itertools.takewhile(bool, reversed_errors))

    @property
    def guardrail_violations(self) -> int:
        """Get the total number of guardrail violations."""
        return sum(
            error == AIResponseErrorType.guardrail_violation
            for error in self.error_event_per_request
        )

    @property
    def sequential_guardrail_violations(self) -> int:
        """Get the number of sequential guardrail violations."""
        reversed_errors = (
            error == AIResponseErrorType.guardrail_violation
            for error in reversed(self.error_event_per_request)
        )
        return sum(itertools.takewhile(bool, reversed_errors))

    async def configure_for_experiment(
        self,
        *,
        experiment_descriptor: ExperimentDescriptor,
        protocol: PlayerProtocol,
        player_uuid: UUID4,
        additional_metadata: dict[str, Any],
    ) -> None:
        """Start tracking an experiment."""
        self.experiment_descriptor = experiment_descriptor
        self.protocol = protocol
        self.player_uuid = player_uuid

        func = partial(
            wandb.init,
            entity=self.wandb_entity,
            project=self.wandb_project,
            config={
                # We call it the `game_id` due to legacy reasons
                "game_id": experiment_descriptor.session_id,
                "game_uuid": experiment_descriptor.game_uuid,
                "player_id": self.player_uuid,
                "experiment_name": experiment_descriptor.experiment_spec.experiment_name,
                **protocol.model_dump(mode="json"),
                **experiment_descriptor.experiment_spec.model_dump(mode="json"),
                **experiment_descriptor.experiment_spec.mission_spec.model_dump(
                    mode="json", by_alias=False
                ),
                **additional_metadata,
            },
            resume="never",
            **self.wandb_init_kwargs,
        )
        _ = await run_sync_in_thread(func)
        self.start_time = Instant.now()
        _logger.info("WandB run started")

    @logfire.instrument("Stop experiment tracker")
    async def on_experiment_stop(self, *, is_hard_crash: bool = False) -> None:
        """Send results to Wandb."""
        data_to_send = self._compute_data_to_send()
        data_to_send["hard_crash"] = is_hard_crash

        # Send tables if they exist
        actions_table = self._compute_actions_table()
        messages_table = self._compute_messages_table()
        do_nothing_table = self._compute_do_nothing_table()
        bomb_states_table = self._compute_bomb_states_table()
        observations_table = await self._compute_observations_table()
        reflections_table = self._compute_reflections_table()
        if reflections_table:
            data_to_send["reflections"] = reflections_table
        if actions_table:
            data_to_send["actions"] = actions_table
        if messages_table:
            data_to_send["messages"] = messages_table
        if do_nothing_table:
            data_to_send["do_nothing_actions"] = do_nothing_table
        if bomb_states_table:
            data_to_send["bomb_states"] = bomb_states_table
        if observations_table:
            data_to_send["observations"] = observations_table

        wandb.log(data_to_send, commit=False)
        self.experiment_descriptor = None
        self.protocol = None

        await self.finish_run(has_crashed=is_hard_crash)
        _logger.debug("WandB run finished")

    @logfire.instrument("Finish WandB run")
    async def finish_run(self, *, has_crashed: bool = False) -> None:
        """Finish the run and clean up."""
        func = partial(wandb.finish, exit_code=1 if has_crashed else 0)
        try:
            await run_sync_in_thread(func)
        except wandb.Error as err:
            if err.message == "You must call wandb.init() before wandb.log()":
                _logger.warning("It seems like the run was never started, skipping finish??")
            else:
                _logger.exception("Error finishing WandB run", error=err)
        _logger.debug("WandB run finished")
        self.reset()

    def start_weave_trace(
        self, message_input: AgentMessageInput, message_history: list[ModelMessage]
    ) -> None:
        """Start a trace to Weave."""
        assert self.protocol is not None, "Player spec must be set before starting a trace."

        inputs: dict[str, Any] = {"history": message_history}
        attributes: dict[str, Any] = {
            "player_id": self.player_uuid,
            **self.protocol.model_dump(mode="json"),
            **self.capabilities.model_dump(mode="json"),
        }

        if self.experiment_descriptor:
            attributes = {
                **attributes,
                "game_id": self.experiment_descriptor.game_uuid,
                "experiment_name": self.experiment_descriptor.experiment_spec.experiment_name,
                **self.experiment_descriptor.experiment_spec.model_dump(mode="json"),
            }

        if self.bomb_states:
            inputs["bomb_states"] = self.bomb_states[-1]

        if isinstance(message_input, str):
            inputs["message_input"] = message_input

        if isinstance(message_input, list):
            inputs["message_input"] = [
                message if isinstance(message, str) else Image.open(io.BytesIO(message.data))
                for message in message_input
            ]

        self._weave_call = self.weave_client.create_call(
            f"{self.capabilities.player_name} ({self.protocol.role})",
            inputs=inputs,
            attributes=attributes,
        )

    def finish_weave_trace(
        self, outputs: PlayerOutputType | str | Any, usage: RunUsage | None
    ) -> None:
        """Finish the trace to Weave."""
        if self._weave_call is None:
            return

        if isinstance(outputs, BaseModel):
            outputs = outputs.model_dump(mode="json")

        usage = usage or RunUsage()

        self.weave_client.finish_call(
            self._weave_call,
            output={
                "usage": {
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.response_tokens,
                    "total_tokens": usage.total_tokens,
                },
                "model": self.capabilities.player_name.lstrip("eu."),
                "output": outputs,
            },
        )
        self._weave_call = None

    @logfire.instrument("Track step {self.num_requests}")
    def step(self, **kwargs: bool | str | None | float) -> None:
        """Step the player with the given kwargs."""
        data_to_send = self._compute_data_to_send()
        with logfire.span("Log with wandb"), suppress(wandb.Error):
            wandb.log(
                {"step": self.num_requests, **data_to_send, **kwargs},
                step=self.num_requests,
                commit=False,
            )

    def reset(self) -> None:  # noqa: WPS213
        """Reset the player data."""
        self.actions.clear()
        self.messages_sent.clear()
        self.bomb_states.clear()
        self.observation_files.clear()
        self.do_nothing_actions.clear()
        self.reflections.clear()
        self.error_event_per_request.clear()
        self.num_invalid_locations = 0
        self.num_prompt_truncations = 0
        self.num_requests = 0

    def add_action(self, action: InteractGameActionType) -> None:
        """Add an action to the player's action list."""
        action_metric = ActionMetric.from_action(
            ktane_action=action, timestamp=self._compute_time_delta()
        )
        self.actions.append(action_metric)

    def add_message(
        self, message: SendMessageAction | SendMessageActionWithThoughts, role: PlayerRole | None
    ) -> None:
        """Add a message to the message list."""
        message_metric = MessageMetric.from_action(
            action=message, role=role, timestamp=self._compute_time_delta()
        )
        self.messages_sent.append(message_metric)

    def add_do_nothing(
        self, action: DoNothingAction | DoNothingActionWithThoughts, role: PlayerRole | None
    ) -> None:
        """Add a do nothing action to the player's action list."""
        nothing_metric = DoNothingMetric.from_action(
            action=action, role=role, timestamp=self._compute_time_delta()
        )
        self.do_nothing_actions.append(nothing_metric)

    def add_bomb_state(self, bomb_state: BombState) -> None:
        """Add the current bomb state for the player."""
        bomb_state_metric = BombStateMetric.from_bomb_state(
            bomb_state=bomb_state, timestamp=self._compute_time_delta()
        )
        self.bomb_states.append(bomb_state_metric)

    async def add_observation(
        self, frames: list[bytes], segm_mask: bytes, som_image: bytes
    ) -> None:
        """Add an observation to the player's observation list."""
        observation_metric = ObservationMetric(
            frames=frames,
            segm_mask=segm_mask,
            som_image=som_image,
            timestamp=self._compute_time_delta(),
        )
        obs_path = self._observations_dir.joinpath(
            f"{self.player_uuid}_{Instant.now().format_common_iso()}.pkl"
        )
        async with await anyio.open_file(obs_path, "wb") as obs_file:
            _ = await obs_file.write(dill.dumps(observation_metric))
        self.observation_files.append(obs_path)
        _logger.info("Observation saved", path=obs_path)

    def add_reflection(self, message: SendMessageAction, role: PlayerRole | None) -> None:
        """Add a reflection message to the player's reflection list."""
        message_metric = MessageMetric.from_action(
            action=message, role=role, timestamp=self._compute_time_delta()
        )
        self.reflections.append(message_metric)

    def add_usage(self, usage: RunUsage) -> None:
        """Add a usage to the player's usage list.

        We need to copy it to avoid mutability issues.
        """
        self.usages.append(deepcopy(usage))

    def should_stop_experiments(self) -> bool:
        """Determine if we should stop the experiment."""
        return any(
            [
                self.sequential_guardrail_violations > self._max_sequential_errors,
                self.sequential_invalid_formats > self._max_sequential_errors,
                self.sequential_server_errors > self._max_sequential_errors,
            ]
        )

    def _compute_data_to_send(self) -> dict[str, Any]:
        data_to_send: dict[str, Any] = {
            "total_defuser_actions": len(self.actions),
            "total_messages_sent": len(self.messages_sent),
            "total_defuser_messages_sent": len(
                [message for message in self.messages_sent if message.role == "defuser"]
            ),
            "total_expert_messages_sent": len(
                [message for message in self.messages_sent if message.role == "expert"]
            ),
            "total_defuser_do_nothing_actions": len(
                [action for action in self.do_nothing_actions if action.role == "defuser"]
            ),
            "total_expert_do_nothing_actions": len(
                [action for action in self.do_nothing_actions if action.role == "expert"]
            ),
            "total_invalid_format": self.num_invalid_formats,
            "total_prompt_truncations": self.num_prompt_truncations,
            "total_guardrail_violations": self.guardrail_violations,
            "total_server_errors": self.num_server_errors,
            **self._compute_usages(),
        }
        if self.bomb_states:
            last_bomb_state = self.bomb_states[-1]

            data_to_send = {
                **data_to_send,
                "is_solved": last_bomb_state.is_solved,
                "is_strike_out": last_bomb_state.is_detonated
                and last_bomb_state.strikes is not None
                and len(last_bomb_state.strikes) >= last_bomb_state.max_strikes,
                "is_timed_out": last_bomb_state.is_detonated
                and last_bomb_state.timer_module.seconds_remaining <= 0,
                "time_remaining": last_bomb_state.timer_module.seconds_remaining,
                "total_modules_solved": len(
                    [module for module in last_bomb_state.modules if module.is_solved]
                ),
                "total_strikes": len(last_bomb_state.strikes) if last_bomb_state.strikes else 0,
                "total_invalid_locations": self.num_invalid_locations,
            }

        return data_to_send

    def _compute_time_delta(self) -> float:
        """Compute the time delta between the start time and now."""
        return (Instant.now() - self.start_time).in_seconds()

    def _compute_bomb_states_table(self) -> wandb.Table | None:
        """Compute the bomb states table."""
        if not self.bomb_states:
            return None
        bomb_states_table = wandb.Table(
            dataframe=pl.from_dicts(
                TypeAdapter(list[BombStateMetric]).dump_python(self.bomb_states, mode="json"),
                schema_overrides=BombStateMetric.polars_schema_override(),
            ).to_pandas(),
            allow_mixed_types=False,
        )
        return bomb_states_table

    def _compute_actions_table(self) -> wandb.Table | None:
        """Compute the actions table."""
        if not self.actions:
            return None
        actions_table = wandb.Table(
            dataframe=pl.from_dicts(
                TypeAdapter(list[ActionMetric]).dump_python(
                    self.actions, mode="json", exclude={"command"}
                )
            ).to_pandas(),
            allow_mixed_types=True,
        )
        return actions_table

    def _compute_messages_table(self) -> wandb.Table | None:
        """Compute the messages table."""
        if not self.messages_sent:
            return None
        messages_table = wandb.Table(
            dataframe=pl.from_dicts(
                TypeAdapter(list[MessageMetric]).dump_python(
                    self.messages_sent, mode="json", exclude={"command"}
                )
            ).to_pandas(),
            allow_mixed_types=True,
        )
        return messages_table

    def _compute_do_nothing_table(self) -> wandb.Table | None:
        """Compute the do nothing actions table."""
        if not self.do_nothing_actions:
            return None
        do_nothing_table = wandb.Table(
            dataframe=pl.from_dicts(
                TypeAdapter(list[DoNothingMetric]).dump_python(
                    self.do_nothing_actions, mode="json", exclude={"command"}
                )
            ).to_pandas(),
            allow_mixed_types=True,
        )
        return do_nothing_table

    async def _compute_observations_table(self) -> wandb.Table | None:
        """Compute the observations table."""
        if not self.observation_files:
            return None
        all_observations = []
        for obs_file in tqdm(self.observation_files, desc="Loading observations"):
            async with await anyio.open_file(obs_file, "rb") as obs_file_handle:  # noqa: WPS476
                file_contents = await obs_file_handle.read()  # noqa: WPS476
                observation = dill.loads(file_contents)  # noqa: S301
                all_observations.append(observation)

        # Use the custom serialiser to convert the images to wandb images
        observations_data = TypeAdapter(list[ObservationMetric]).dump_python(
            all_observations, context={"wandb": True}
        )
        observations_table = wandb.Table(
            columns=["frames", "segmentation_mask", "som_image", "timestamp"]
        )
        for row in observations_data:
            observations_table.add_data(
                row["frames"], row["segmentation_mask"], row["som_image"], row["timestamp"]
            )
        return observations_table

    def _compute_reflections_table(self) -> wandb.Table | None:
        """Compute the reflections table."""
        if not self.reflections:
            return None
        reflections_table = wandb.Table(
            dataframe=pl.from_dicts(
                TypeAdapter(list[MessageMetric]).dump_python(
                    self.reflections, mode="json", exclude={"command"}
                )
            ).to_pandas(),
            allow_mixed_types=True,
        )
        return reflections_table

    def _compute_usages(self) -> dict[str, int]:
        """Compute the usages."""
        usage = RunUsage()
        for next_usage in self.usages:  # noqa: WPS519
            usage += next_usage
        return {f"total_{key}": count for key, count in asdict(usage).items()}
