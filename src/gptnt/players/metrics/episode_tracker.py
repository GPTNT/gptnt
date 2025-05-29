import io
import itertools
from contextlib import suppress
from dataclasses import dataclass, field
from functools import partial
from typing import Any

import polars as pl
import wandb
import weave
from PIL import Image
from pydantic import BaseModel, TypeAdapter
from pydantic.types import UUID4
from pydantic_ai.messages import ModelMessage
from pydantic_ai.usage import Usage
from structlog import get_logger
from weave.trace.weave_client import WeaveClient
from whenever import Instant

from gptnt.api.experiment_manager.experiment_descriptor import ExperimentDescriptor
from gptnt.common.async_ops import run_in_separate_thread
from gptnt.ktane.state.bomb import BombState
from gptnt.players.actions import (
    DoNothingAction,
    DoNothingActionWithThoughts,
    InteractGameActionType,
    PlayerOutputType,
    SendMessageAction,
    SendMessageActionWithThoughts,
)
from gptnt.players.messages import AgentMessageInput
from gptnt.players.metrics.structures import (
    ActionMetric,
    BombStateMetric,
    DoNothingMetric,
    MessageMetric,
    ObservationMetric,
)
from gptnt.players.spec import PlayerMetadata, PlayerRole, PlayerSpec

_logger = get_logger()


@dataclass(kw_only=True)
class EpisodeTracker:
    """Tracks metrics for an episode."""

    wandb_path: str
    """Path to the WandB project, e.g. `entity/project`."""

    wandb_init_kwargs: dict[str, Any] = field(default_factory=dict)
    """Keyword arguments for initializing WandB."""

    weave_client: WeaveClient = field(init=False, repr=False)
    """Weave client for tracing."""
    _weave_call: Any | None = field(default=None, init=False, repr=False)

    player_metadata: PlayerMetadata
    """Metadata about the player.

    This is constant for the player so it can be given up front.
    """
    player_uuid: UUID4 = field(init=False, repr=False)

    experiment_descriptor: ExperimentDescriptor | None = field(default=None, init=False)
    player_spec: PlayerSpec | None = field(default=None, init=False)

    start_time: Instant = field(init=False, repr=False)

    # Counters
    num_requests: int = field(default=0, init=False)
    num_invalid_locations: int = field(default=0, init=False)
    """Number of invalid SoM locations."""
    num_invalid_formats: int = field(default=0, init=False)
    """Number of invalid output formats."""
    num_prompt_truncations: int = field(default=0, init=False)
    """Number of prompt truncations (because it got too long)."""

    # Trackers
    guardrail_violations_per_request: list[bool] = field(default_factory=list, init=False)
    """Number of guardrail/safety violations."""

    actions: list[ActionMetric] = field(default_factory=list, init=False)
    messages_sent: list[MessageMetric] = field(default_factory=list, init=False)
    do_nothing_actions: list[DoNothingMetric] = field(default_factory=list, init=False)
    bomb_states: list[BombStateMetric] = field(default_factory=list, init=False)
    observations: list[ObservationMetric] = field(default_factory=list, init=False)
    reflections: list[MessageMetric] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        """Initialize the Weave client and WandB."""
        self.weave_client = weave.init(project_name=self.wandb_path)

    @property
    def guardrail_violations(self) -> int:
        """Get the total number of guardrail violations."""
        return sum(self.guardrail_violations_per_request)

    @property
    def sequential_guardrail_violations(self) -> int:
        """Get the number of sequential guardrail violations."""
        return sum(itertools.takewhile(bool, reversed(self.guardrail_violations_per_request)))

    async def on_experiment_start(
        self,
        *,
        experiment_descriptor: ExperimentDescriptor,
        player_spec: PlayerSpec,
        additional_metadata: dict[str, Any],
    ) -> None:
        """Start tracking an experiment."""
        self.experiment_descriptor = experiment_descriptor
        self.player_spec = player_spec

        func = partial(
            wandb.init,
            entity=self.wandb_path.split("/")[0],
            project=self.wandb_path.split("/")[1],
            config={
                "game_id": experiment_descriptor.game_uuid,
                "room_id": experiment_descriptor.room_uuid,
                "player_id": self.player_uuid,
                "experiment_name": experiment_descriptor.experiment_spec.experiment_name,
                **player_spec.model_dump(mode="json"),
                **experiment_descriptor.experiment_spec.model_dump(mode="json"),
                **experiment_descriptor.experiment_spec.mission_spec.model_dump(
                    mode="json", by_alias=False
                ),
                **additional_metadata,
            },
            resume="never",
            **self.wandb_init_kwargs,
        )
        await run_in_separate_thread(func)
        self.start_time = Instant.now()
        _logger.info("WandB run started")

    async def on_experiment_stop(self, *, is_hard_crash: bool = False) -> None:
        """Send results to Wandb."""
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
            "hard_crash": is_hard_crash,
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
            }

        # Send tables if they exist
        actions_table = self._compute_actions_table()
        messages_table = self._compute_messages_table()
        do_nothing_table = self._compute_do_nothing_table()
        bomb_states_table = self._compute_bomb_states_table()
        observations_table = self._compute_observations_table()
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
        self.player_spec = None

        await self.finish_run(has_crashed=is_hard_crash)
        _logger.debug("WandB run finished")

    async def finish_run(self, *, has_crashed: bool = False) -> None:
        """Finish the run and clean up."""
        func = partial(wandb.finish, exit_code=1 if has_crashed else 0)
        await run_in_separate_thread(func)
        _logger.debug("WandB run finished")
        self.reset()

    def start_weave_trace(
        self, message_input: AgentMessageInput, message_history: list[ModelMessage]
    ) -> None:
        """Start a trace to Weave."""
        assert self.player_spec is not None, "Player spec must be set before starting a trace."

        inputs: dict[str, Any] = {"history": message_history}
        attributes: dict[str, Any] = {
            "player_id": self.player_uuid,
            **self.player_spec.model_dump(mode="json"),
            **self.player_metadata.model_dump(mode="json"),
        }

        if self.experiment_descriptor:
            attributes = {
                **attributes,
                "game_id": self.experiment_descriptor.game_uuid,
                "room_id": self.experiment_descriptor.room_uuid,
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
            f"{self.player_metadata.player_name} ({self.player_spec.role})",
            inputs=inputs,
            attributes=attributes,
        )

    def finish_weave_trace(
        self, outputs: PlayerOutputType | str | Any, usage: Usage | None
    ) -> None:
        """Finish the trace to Weave."""
        if self._weave_call is None:
            return

        if isinstance(outputs, BaseModel):
            outputs = outputs.model_dump(mode="json")

        usage = usage or Usage()

        self.weave_client.finish_call(
            self._weave_call,
            output={
                "usage": {
                    "input_tokens": usage.request_tokens,
                    "output_tokens": usage.response_tokens,
                    "total_tokens": usage.total_tokens,
                },
                "model": self.player_metadata.player_name.lstrip("eu."),
                "output": outputs,
            },
        )
        self._weave_call = None

    def step(self, **kwargs: bool | str | None | float) -> None:
        """Step the player with the given kwargs."""
        with suppress(wandb.Error):
            wandb.log(
                {
                    "step": self.num_requests,
                    "total_prompt_truncations": self.num_prompt_truncations,
                    **kwargs,
                },
                commit=False,
            )

    def reset(self) -> None:
        """Reset the player data."""
        self.actions.clear()
        self.messages_sent.clear()
        self.bomb_states.clear()
        self.observations.clear()
        self.do_nothing_actions.clear()
        self.reflections.clear()
        self.guardrail_violations_per_request.clear()
        self.num_invalid_locations = 0
        self.num_invalid_formats = 0
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

    def add_observation(self, frames: list[bytes], segm_mask: bytes, som_image: bytes) -> None:
        """Add an observation to the player's observation list."""
        observation_metric = ObservationMetric(
            frames=frames,
            segm_mask=segm_mask,
            som_image=som_image,
            timestamp=self._compute_time_delta(),
        )
        self.observations.append(observation_metric)

    def add_reflection(self, message: SendMessageAction, role: PlayerRole | None) -> None:
        """Add a reflection message to the player's reflection list."""
        message_metric = MessageMetric.from_action(
            action=message, role=role, timestamp=self._compute_time_delta()
        )
        self.reflections.append(message_metric)

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

    def _compute_observations_table(self) -> wandb.Table | None:
        """Compute the observations table."""
        if not self.observations:
            return None
        # Use the custom serialiser to convert the images to wandb images
        observations_data = TypeAdapter(list[ObservationMetric]).dump_python(
            self.observations, context={"wandb": True}
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
