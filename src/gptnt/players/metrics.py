from typing import TYPE_CHECKING, Any, Self, cast

import logfire
import polars as pl
import wandb
from pandas import json_normalize
from pydantic import BaseModel, SerializationInfo, TypeAdapter, field_serializer, model_serializer
from whenever import Instant

from gptnt.common.image_ops import load_observation_from_bytes
from gptnt.ktane.experiments.experiments import ExperimentSpec
from gptnt.ktane.state.bomb import BombState
from gptnt.ktane.state.modules import ModuleStates
from gptnt.ktane.state.widget import WidgetStates
from gptnt.players.actions import InteractGameAction, InteractGameLocation, SendMessageAction
from gptnt.players.structures import PlayerRole

if TYPE_CHECKING:
    from wandb.sdk.wandb_run import Run


def flatten_dict(config: dict[str, Any], *, separator: str = ".") -> dict[str, Any]:
    """Flatten dictionaries to dot notation."""
    # Although this flattens it, it creates a dataframe for the output
    normalized_config = json_normalize(config, sep=separator)

    # Convert the dataframe which only has a single row into the output format we want
    flattened_config_as_dict = normalized_config.to_dict(orient="records")[0]
    return cast("dict[str, Any]", flattened_config_as_dict)


class TimestampMixin(BaseModel):
    """Mixin class to add a timestamp to the model."""

    timestamp: float


class ActionMetric(InteractGameAction[InteractGameLocation], TimestampMixin):
    """Action metric class for observability logging."""

    @classmethod
    def from_action(
        cls, *, ktane_action: InteractGameAction[InteractGameLocation], timestamp: float
    ) -> Self:
        """Create an ActionMetric from an InteractGameAction."""
        return cls(
            action=ktane_action.action,
            location=ktane_action.location,
            thoughts=ktane_action.thoughts,
            timestamp=timestamp,
        )


class MessageMetric(SendMessageAction, TimestampMixin):
    """SendMessageAction for logging."""

    role: PlayerRole | None

    @classmethod
    def from_action(
        cls, *, action: SendMessageAction, role: PlayerRole | None, timestamp: float
    ) -> Self:
        """Create a MessageMetric from an SendMessageAction."""
        return cls(
            message=action.message, role=role, thoughts=action.thoughts, timestamp=timestamp
        )


class BombStateMetric(BombState, TimestampMixin):
    """Bomb state metric class for observability logging."""

    @classmethod
    def from_bomb_state(cls, *, bomb_state: BombState, timestamp: float) -> Self:
        """Instantiate from a BombState.

        Because BombState is a subclass of this class, we just set the timestamp and pass it in
        because it should work. This is a bit of a hack, but it works.
        """
        return cls.model_validate({**bomb_state.model_dump(), "timestamp": timestamp})

    @classmethod
    def polars_schema_override(cls) -> dict[str, Any]:
        """Override the schema for the polars dataframe to build a consistent table."""
        return {
            "seed": pl.Int32,
            "max_strikes": pl.Int32,
            "current_strikes": pl.Int32,
            "strikes": pl.List(pl.String),
            "is_detonated": pl.Boolean,
            "is_solved": pl.Boolean,
            "is_light_on": pl.Boolean,
            "timer_module": pl.Struct(
                fields={
                    "name": pl.String,
                    "on_front": pl.Boolean,
                    "index": pl.Int32,
                    "seconds_remaining": pl.Float32,
                }
            ),
            "widgets": pl.String,
            "modules": pl.String,
        }

    @field_serializer("modules")
    def serialize_modules(self, modules: list[ModuleStates]) -> str:
        """Serialize the modules to a string."""
        return TypeAdapter(list[ModuleStates]).dump_json(modules).decode("utf-8")

    @field_serializer("widgets")
    def serialize_widgets(self, widgets: list[WidgetStates]) -> str:
        """Serialize the widgets to a string."""
        return TypeAdapter(list[WidgetStates]).dump_json(widgets).decode("utf-8")


class ObservationMetric(TimestampMixin):
    """Observation metric class for observability logging."""

    raw_image: bytes
    segm_mask: bytes | None
    som_image: bytes

    @classmethod
    def from_observation(
        cls, *, raw_image: bytes, segm_mask: bytes, som_image: bytes, timestamp: float
    ) -> Self:
        """Create an ObservationMetric from an observation."""
        return cls(
            raw_image=raw_image,
            segm_mask=segm_mask if segm_mask else None,
            som_image=som_image,
            timestamp=timestamp,
        )

    @model_serializer(mode="plain")
    def serialize_wandb(self, info: SerializationInfo) -> dict[str, Any]:  # noqa: WPS110
        """Serialize the observation to a WandB image."""
        context = info.context
        if context is None:
            return self.model_dump()
        is_for_wandb = context.get("wandb", False) is not None
        if is_for_wandb:
            # If we are in a wandb context, we need to convert the images to wandb images
            return self._to_wandb_images()
        return self.model_dump()

    def _to_wandb_images(self) -> dict[str, Any]:
        # Convert the images to WandB images
        raw_image = wandb.Image(load_observation_from_bytes(self.raw_image), caption="Raw Image")
        segm_mask = (
            wandb.Image(load_observation_from_bytes(self.segm_mask), caption="Segmentation Mask")
            if self.segm_mask
            else None
        )
        som_image = wandb.Image(load_observation_from_bytes(self.som_image), caption="SoM Image")

        return {
            "raw_image": raw_image,
            "segmentation_mask": segm_mask,
            "som_image": som_image,
            "timestamp": self.timestamp,
        }


class PlayerEpisodeTracker:
    """Track an entire game for a single game and set it to WandB."""

    def __init__(self, *, wandb_init_kwargs: dict[str, Any]) -> None:
        self._wandb_init_kwargs = wandb_init_kwargs

        self._run: Run
        self._actions: list[ActionMetric] = []
        self._messages_sent: list[MessageMetric] = []
        self._bomb_states: list[BombStateMetric] = []
        self._observations: list[ObservationMetric] = []

        self.start_time: Instant

    def on_game_start(
        self,
        *,
        experiment_spec: ExperimentSpec,
        game_id: str,
        player_id: str,
        role: PlayerRole | None,
        additional_metadata: dict[str, Any],
    ) -> None:
        """Start the run for the current player.

        All configs given are flattened using dot notation.
        """
        self._run = wandb.init(
            config=flatten_dict(
                {
                    "game_id": game_id,
                    "player_id": player_id,
                    "role": role,
                    "experiment_spec": experiment_spec.model_dump(mode="json"),
                    **additional_metadata,
                }
            ),
            **self._wandb_init_kwargs,
        )
        self.start_time = Instant.now()

    @logfire.instrument("Send results to wandb")
    def on_game_end(self) -> None:
        """Sends the mission results to wandb and cleans up."""
        actions_table, messages_table, bomb_states_table, observations_table = (
            self._compute_tables()
        )

        last_bomb_state = self._bomb_states[-1]

        self._run.log(
            {
                # tables
                "actions": actions_table,
                "messages": messages_table,
                "bomb_states": bomb_states_table,
                "observations": observations_table,
                # other metrics
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
                "total_defuser_actions": len(self._actions),
                "total_messages_sent": len(self._messages_sent),
                "total_defuser_messages_sent": len(
                    [message for message in self._messages_sent if message.role == "defuser"]
                ),
                "total_expert_messages_sent": len(
                    [message for message in self._messages_sent if message.role == "expert"]
                ),
            }
        )
        self._run.finish()
        self._reset()

    def add_action(self, action: InteractGameAction[InteractGameLocation]) -> None:
        """Add an action to the player's action list."""
        action_metric = ActionMetric.from_action(
            ktane_action=action, timestamp=self._compute_time_delta()
        )
        self._actions.append(action_metric)

    def add_message(self, message: SendMessageAction, role: PlayerRole | None) -> None:
        """Add a message to the message list."""
        message_metric = MessageMetric.from_action(
            action=message, role=role, timestamp=self._compute_time_delta()
        )
        self._messages_sent.append(message_metric)

    def add_bomb_state(self, bomb_state: BombState) -> None:
        """Add the current bomb state for the player."""
        bomb_state_metric = BombStateMetric.from_bomb_state(
            bomb_state=bomb_state, timestamp=self._compute_time_delta()
        )
        self._bomb_states.append(bomb_state_metric)

    def add_observation(self, raw_image: bytes, segm_mask: bytes, som_image: bytes) -> None:
        """Add an observation to the player's observation list."""
        observation_metric = ObservationMetric.from_observation(
            raw_image=raw_image,
            segm_mask=segm_mask,
            som_image=som_image,
            timestamp=self._compute_time_delta(),
        )
        self._observations.append(observation_metric)

    def _reset(self) -> None:
        """Reset the player data."""
        self._actions.clear()
        self._messages_sent.clear()
        self._bomb_states.clear()
        self._observations.clear()

    def _compute_tables(self) -> tuple[wandb.Table, wandb.Table, wandb.Table, wandb.Table]:  # noqa: WPS210
        """Convert player data to a W&B Table for logging."""
        # Messages table
        messages_table = wandb.Table(
            dataframe=pl.from_dicts(
                TypeAdapter(list[MessageMetric]).dump_python(
                    self._messages_sent, mode="json", exclude={"action_type"}
                )
            ).to_pandas(),
            allow_mixed_types=True,
        )

        # Bomb states
        bomb_states_table = wandb.Table(
            dataframe=pl.from_dicts(
                TypeAdapter(list[BombStateMetric]).dump_python(self._bomb_states, mode="json"),
                schema_overrides=BombStateMetric.polars_schema_override(),
            ).to_pandas(),
            allow_mixed_types=False,
        )

        # in-game actions
        actions_table = wandb.Table(
            dataframe=pl.from_dicts(
                TypeAdapter(list[ActionMetric]).dump_python(
                    self._actions, mode="json", exclude={"action_type"}
                )
            ).to_pandas(),
            allow_mixed_types=True,
        )

        # Use the custom serialiser to convert the images to wandb images
        observations_data = TypeAdapter(list[ObservationMetric]).dump_python(
            self._observations, context={"wandb": True}
        )

        # Observations table
        observations_table = wandb.Table(
            columns=["raw_image", "segmentation_mask", "som_image", "timestamp"]
        )
        for row in observations_data:
            observations_table.add_data(
                row["raw_image"], row["segmentation_mask"], row["som_image"], row["timestamp"]
            )

        return actions_table, messages_table, bomb_states_table, observations_table

    def _compute_time_delta(self) -> float:
        """Compute the time delta between the start time and now."""
        return (Instant.now() - self.start_time).in_seconds()
