from typing import TYPE_CHECKING, Any, Literal, Self, cast

import polars as pl
import wandb
from pydantic import BaseModel, TypeAdapter

from gptnt.ktane.experiments.experiments import ExperimentSpec
from gptnt.ktane.state.bomb import BombState
from gptnt.players.actions import InteractGameAction, InteractGameLocation, SendMessageAction

if TYPE_CHECKING:
    from wandb.sdk.wandb_run import Run

from pandas import json_normalize
from whenever import Instant

type Role = Literal["defuser", "expert"]


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

    role: Role

    @classmethod
    def from_action(cls, *, action: SendMessageAction, role: Role, timestamp: float) -> Self:
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
        return cls.model_construct(None, timestamp=timestamp, **bomb_state.model_dump())


class ObservationMetric(BaseModel):
    """Observation metric class for observability logging."""

    raw_image: bytes
    segm_mask: bytes | None
    final_image: bytes
    timestamp: float


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
        role: Role,
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

    def on_game_end(self) -> None:
        """Sends the mission results to wandb and cleans up."""
        actions_table, messages_table, bomb_states_table = self._compute_tables()

        self._run.log(
            {
                "actions_data": actions_table,
                "messages_data": messages_table,
                "bomb_states_data": bomb_states_table,
                "is_solved": self._bomb_states[-1].is_solved if self._bomb_states else None,
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

    def add_message(self, message: SendMessageAction, role: Role) -> None:
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

    def add_observation(self, observation: bytes) -> None:
        """Add an observation to the player's observation list."""
        # TODO: Change to a more appropriate type
        raise NotImplementedError("Observation metric is not implemented yet.")

    def _reset(self) -> None:
        """Reset the player data."""
        self._actions.clear()
        self._messages_sent.clear()
        self._bomb_states.clear()
        self._observations.clear()

    def _compute_tables(self) -> tuple[wandb.Table, wandb.Table, wandb.Table]:
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
                TypeAdapter(list[BombStateMetric]).dump_python(self._bomb_states, mode="json")
            ).to_pandas(),
            allow_mixed_types=True,
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

        return actions_table, messages_table, bomb_states_table

    def _compute_time_delta(self) -> float:
        """Compute the time delta between the start time and now."""
        return (Instant.now() - self.start_time).in_seconds()
