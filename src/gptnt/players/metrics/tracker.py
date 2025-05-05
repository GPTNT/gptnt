from contextlib import suppress
from functools import partial
from typing import Any

import logfire
import polars as pl
import wandb
from pydantic import UUID4, TypeAdapter
from structlog import get_logger
from whenever import Instant

from gptnt.common.async_ops import run_in_separate_thread
from gptnt.ktane.experiments.experiments import ExperimentSpec
from gptnt.ktane.state.bomb import BombState
from gptnt.players.actions import InteractGameAction, InteractGameLocation, SendMessageAction
from gptnt.players.metrics.structures import (
    ActionMetric,
    AdditionalEndGameMetrics,
    BombStateMetric,
    MessageMetric,
    ObservationMetric,
)
from gptnt.players.metrics.wandb import flatten_dict
from gptnt.players.structures import PlayerRole

_logger = get_logger()


class PlayerEpisodeTracker:
    """Track an entire game for a single game and set it to WandB."""

    def __init__(self, *, wandb_init_kwargs: dict[str, Any]) -> None:
        self._wandb_init_kwargs = wandb_init_kwargs

        self._actions: list[ActionMetric] = []
        self._messages_sent: list[MessageMetric] = []
        self._bomb_states: list[BombStateMetric] = []
        self._observations: list[ObservationMetric] = []
        self._reflections: list[MessageMetric] = []

        self.num_invalid_formats: int = 0
        self.num_prompt_truncations: int = 0
        self.guardrail_violations: int = 0

        self.start_time: Instant

    def on_game_start(
        self,
        *,
        experiment_spec: ExperimentSpec,
        game_id: UUID4,
        player_id: UUID4,
        role: PlayerRole | None,
        additional_metadata: dict[str, Any],
    ) -> None:
        """Start the run for the current player.

        All configs given are flattened using dot notation.
        """
        run = wandb.init(
            config=flatten_dict(
                {
                    "game_id": game_id,
                    "player_id": player_id,
                    "role": role,
                    "experiment_name": experiment_spec.experiment_name,
                    "resume": "never",
                    **experiment_spec.model_dump(mode="json"),
                    **additional_metadata,
                }
            ),
            **self._wandb_init_kwargs,
        )
        _logger.info("WandB run started", run_id=run.id, config=run.config)
        self.start_time = Instant.now()

    @logfire.instrument("Send results to wandb")
    async def on_game_end(
        self, *, additional_end_game_metrics: AdditionalEndGameMetrics | None = None
    ) -> None:
        """Sends the mission results to wandb and cleans up."""
        additional_end_game_metrics = additional_end_game_metrics or AdditionalEndGameMetrics()
        data_to_send: dict[str, Any] = {
            "total_defuser_actions": len(self._actions),
            "total_messages_sent": len(self._messages_sent),
            "total_defuser_messages_sent": len(
                [message for message in self._messages_sent if message.role == "defuser"]
            ),
            "total_expert_messages_sent": len(
                [message for message in self._messages_sent if message.role == "expert"]
            ),
            "total_invalid_format": self.num_invalid_formats,
            "total_prompt_truncations": self.num_prompt_truncations,
            "total_guardrail_violations": self.guardrail_violations,
            **additional_end_game_metrics.model_dump(mode="json"),
        }

        if self._bomb_states:
            last_bomb_state = self._bomb_states[-1]

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
        bomb_states_table = self._compute_bomb_states_table()
        observations_table = self._compute_observations_table()
        reflections_table = self._compute_reflections_table()
        if reflections_table:
            data_to_send["reflections"] = reflections_table
        if actions_table:
            data_to_send["actions"] = actions_table
        if messages_table:
            data_to_send["messages"] = messages_table
        if bomb_states_table:
            data_to_send["bomb_states"] = bomb_states_table
        if observations_table:
            data_to_send["observations"] = observations_table

        wandb.log(data_to_send, commit=False)

        await self.finish_run(has_crashed=additional_end_game_metrics.has_crashed)
        _logger.debug("WandB run finished")

    @logfire.instrument("Finish wandb run")
    async def finish_run(self, *, has_crashed: bool = False) -> None:
        """Finish the run and clean up."""
        func = partial(wandb.finish, exit_code=1 if has_crashed else 0)
        with logfire.span("Sending data to wandb"):
            await run_in_separate_thread(func)
        _logger.debug("WandB run finished")

        self.reset()

    def step(self, **kwargs: bool | str | None | float) -> None:
        """Step the player with the given kwargs."""
        with suppress(wandb.Error):
            wandb.log(kwargs)

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

    def add_observation(self, frames: list[bytes], segm_mask: bytes, som_image: bytes) -> None:
        """Add an observation to the player's observation list."""
        observation_metric = ObservationMetric(
            frames=frames,
            segm_mask=segm_mask,
            som_image=som_image,
            timestamp=self._compute_time_delta(),
        )
        self._observations.append(observation_metric)

    def add_reflection(self, message: SendMessageAction, role: PlayerRole | None) -> None:
        """Add a reflection message to the player's reflection list."""
        message_metric = MessageMetric.from_action(
            action=message, role=role, timestamp=self._compute_time_delta()
        )
        self._reflections.append(message_metric)

    def reset(self) -> None:
        """Reset the player data."""
        self._actions.clear()
        self._messages_sent.clear()
        self._bomb_states.clear()
        self._observations.clear()

    def _compute_time_delta(self) -> float:
        """Compute the time delta between the start time and now."""
        return (Instant.now() - self.start_time).in_seconds()

    def _compute_bomb_states_table(self) -> wandb.Table | None:
        """Compute the bomb states table."""
        if not self._bomb_states:
            return None
        bomb_states_table = wandb.Table(
            dataframe=pl.from_dicts(
                TypeAdapter(list[BombStateMetric]).dump_python(self._bomb_states, mode="json"),
                schema_overrides=BombStateMetric.polars_schema_override(),
            ).to_pandas(),
            allow_mixed_types=False,
        )
        return bomb_states_table

    def _compute_actions_table(self) -> wandb.Table | None:
        """Compute the actions table."""
        if not self._actions:
            return None
        actions_table = wandb.Table(
            dataframe=pl.from_dicts(
                TypeAdapter(list[ActionMetric]).dump_python(
                    self._actions, mode="json", exclude={"action_type"}
                )
            ).to_pandas(),
            allow_mixed_types=True,
        )
        return actions_table

    def _compute_messages_table(self) -> wandb.Table | None:
        """Compute the messages table."""
        if not self._messages_sent:
            return None
        messages_table = wandb.Table(
            dataframe=pl.from_dicts(
                TypeAdapter(list[MessageMetric]).dump_python(
                    self._messages_sent, mode="json", exclude={"action_type"}
                )
            ).to_pandas(),
            allow_mixed_types=True,
        )
        return messages_table

    def _compute_observations_table(self) -> wandb.Table | None:
        """Compute the observations table."""
        if not self._observations:
            return None
        # Use the custom serialiser to convert the images to wandb images
        observations_data = TypeAdapter(list[ObservationMetric]).dump_python(
            self._observations, context={"wandb": True}
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
        if not self._reflections:
            return None
        reflections_table = wandb.Table(
            dataframe=pl.from_dicts(
                TypeAdapter(list[MessageMetric]).dump_python(
                    self._reflections, mode="json", exclude={"action_type"}
                )
            ).to_pandas(),
            allow_mixed_types=True,
        )
        return reflections_table
