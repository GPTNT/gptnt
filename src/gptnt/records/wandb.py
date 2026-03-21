from contextlib import suppress
from dataclasses import dataclass, field
from functools import partial
from typing import Any, override

import logfire
import pandas as pd
import structlog
import wandb
from anyio.to_thread import run_sync as run_sync_in_thread
from pydantic import UUID4
from pydantic_ai import ModelMessage

from gptnt.common.image_ops import load_observation_from_bytes
from gptnt.ktane.actions import KtaneGameplayInput
from gptnt.players.actions import AgentCallResult, PlayerOutputType
from gptnt.players.observation_handler import Observation
from gptnt.players.specification import PlayerProtocol
from gptnt.records.models import ExperimentStepRecord
from gptnt.records.recorder import ExperimentPlayerRecorder
from gptnt.services.experiment_descriptor import ExperimentDescriptor

logger = structlog.get_logger()


def serialise_observation_for_wandb(obs: Observation) -> dict[str, Any]:  # noqa: WPS110
    """Serialize an Observation for WandB logging."""
    frames = [
        wandb.Image(
            load_observation_from_bytes(obs.frames[frame_index]), caption=f"Frame {frame_index}"
        )
        for frame_index in range(len(obs.frames))
    ]
    segm_mask = (
        wandb.Image(load_observation_from_bytes(obs.segm_mask), caption="Segmentation Mask")
        if obs.segm_mask
        else None
    )
    som_image = wandb.Image(load_observation_from_bytes(obs.som_image), caption="SoM Image")
    return {"frames": frames, "segm_mask": segm_mask, "som_image": som_image}


def convert_records_to_wandb_table(step_records: list[ExperimentStepRecord]) -> wandb.Table:
    """Convert a list of ExperimentStepRecord to a WandB Table.

    Importantly, the records sent to wandb are not the same as those stored on disk because we will
    likely run out of storage on wandb. We do not include the input/new messages in full.
    """
    table_data = [
        record.model_dump(
            mode="json",
            exclude={"observation", "input_messages", "new_messages"},
            context={"serialize_as_string": True},
        )
        for record in step_records
    ]
    as_dataframe = pd.DataFrame(table_data)
    wandb_table = wandb.Table(dataframe=as_dataframe, allow_mixed_types=True)

    all_obs = [
        serialise_observation_for_wandb(record.observation)
        if isinstance(record.observation, Observation)
        else {"frames": None, "segm_mask": None, "som_image": None}
        for record in step_records
    ]
    if all_obs:
        # convert to list for each column
        wandb_table.add_column("frames", [obs["frames"] for obs in all_obs], optional=True)
        wandb_table.add_column("segm_masks", [obs["segm_mask"] for obs in all_obs], optional=True)
        wandb_table.add_column("som_images", [obs["som_image"] for obs in all_obs], optional=True)

    return wandb_table


@dataclass(kw_only=True)
class WandbExperimentPlayerRecorder(ExperimentPlayerRecorder):
    """Experiment tracker that logs to WandB.

    This class extends the base ExperimentTracker to add WandB-specific logging.
    """

    wandb_entity: str
    wandb_project: str

    wandb_init_kwargs: dict[str, Any] = field(default_factory=dict)
    """Keyword arguments for initializing WandB."""

    @override
    async def configure_for_experiment(
        self,
        *,
        experiment_descriptor: ExperimentDescriptor,
        protocol: PlayerProtocol,
        player_uuid: UUID4,
    ) -> None:
        await super().configure_for_experiment(
            experiment_descriptor=experiment_descriptor, protocol=protocol, player_uuid=player_uuid
        )
        func = partial(
            wandb.init,
            entity=self.wandb_entity,
            project=self.wandb_project,
            config={
                "session_id": experiment_descriptor.session_id,
                "game_uuid": experiment_descriptor.game_uuid,
                "player_uuid": self.player_uuid,
                "experiment_name": experiment_descriptor.experiment_spec.experiment_name,
                "attempt": experiment_descriptor.experiment_spec.attempt,
                "attempt_name": experiment_descriptor.experiment_spec.attempt_name,
                **protocol.model_dump(mode="json"),
                **experiment_descriptor.experiment_spec.model_dump(mode="json"),
                **experiment_descriptor.experiment_spec.mission_spec.model_dump(
                    mode="json", by_alias=False
                ),
            },
            resume="never",
            **self.wandb_init_kwargs,
        )
        _ = await run_sync_in_thread(func)
        logger.info("WandB run started")

    @override
    def track_step(
        self,
        *,
        agent_call_result: AgentCallResult[PlayerOutputType | KtaneGameplayInput],
        num_prompt_truncations: int,
        input_messages: list[ModelMessage],
        is_reflection: bool = False,
        **kwargs: bool | str | None | float,
    ) -> None:
        super().track_step(
            agent_call_result=agent_call_result,
            num_prompt_truncations=num_prompt_truncations,
            input_messages=input_messages,
            is_reflection=is_reflection,
        )
        # Log step to WandB
        data_to_send = self._compute_data_to_send()
        with logfire.span("Log with wandb"), suppress(wandb.Error):
            wandb.log(
                {"step": self.num_steps, **data_to_send, **kwargs},
                step=self.num_steps,
                commit=False,
            )

    @override
    @logfire.instrument("Stop experiment tracker", extract_args=["is_hard_crash"])
    async def on_experiment_stop(self, *, is_hard_crash: bool = False) -> None:
        player_record = self.build_player_record(is_hard_crash=is_hard_crash)
        player_record = await player_record.rebuild_with_observations()
        await self.save_player_record_to_disk(player_record=player_record)

        data_to_send = self._compute_data_to_send()
        data_to_send["step_records"] = convert_records_to_wandb_table(player_record.step_records)

        wandb.log(data_to_send, commit=False)
        await self.finish_run(has_crashed=is_hard_crash)
        self.reset()

    @logfire.instrument("Finish WandB run", extract_args=["has_crashed"])
    async def finish_run(self, *, has_crashed: bool = False) -> None:
        """Finish the run and clean up."""
        func = partial(wandb.finish, exit_code=1 if has_crashed else 0)
        try:
            await run_sync_in_thread(func)
        except wandb.Error as err:
            if err.message == "You must call wandb.init() before wandb.log()":
                logger.warning("It seems like the run was never started, skipping finish??")
            else:
                logger.exception("Error finishing WandB run", error=err)
        logger.debug("WandB run finished")

    def _compute_data_to_send(self) -> dict[str, Any]:
        """Compute the data to send to WandB."""
        player_record = self.build_player_record()
        player_record_json = player_record.model_dump(
            mode="json", exclude={"step_records", "experiment_descriptor", "player_content"}
        )

        data_to_send = {**player_record_json}
        # Remove None values
        data_to_send = {key: metric for key, metric in data_to_send.items() if metric is not None}

        return data_to_send
