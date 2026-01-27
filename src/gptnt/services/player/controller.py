from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Literal

import anyio
import logfire
import structlog
from anyio.abc import TaskGroup
from fastapi import HTTPException
from faststream.redis import RedisBroker
from pydantic import BaseModel

from gptnt.common.paths import Paths
from gptnt.ktane.actions import KtaneGameplayInput
from gptnt.ktane.manual import KtaneManualPaths
from gptnt.players.actions import AgentCallResult, PlayerOutputType
from gptnt.players.ai.input_builder import AgentInputBuilder
from gptnt.players.ai.messages.message_history import MessageHistory
from gptnt.players.feedback.nobf import NaughtyOutputBehaviourFeedbackGenerator
from gptnt.players.specification import PlayerProtocol
from gptnt.prompts.manual import load_manual_as_prompt
from gptnt.prompts.prompt_cache import PromptCache
from gptnt.services.events.player import PlayerMessage, PlayerState, StopPlayerEvent
from gptnt.services.experiment_descriptor import ExperimentDescriptor
from gptnt.services.player.supervisor import PlayerSupervisor

logger = structlog.get_logger()

PlayerCommand = Literal[
    "configure_for_experiment",
    "forward_pass",
    "stop",
    "reset",
    "reflection",
    "send_feedback",
    "get_state",
]


class _ConfigureExperimentPayload(BaseModel):
    protocol: PlayerProtocol
    experiment_descriptor: ExperimentDescriptor


@dataclass(kw_only=True)
class PlayerController(PlayerSupervisor):
    """Controller for the player service with all Redis RPC command handlers."""

    broker: RedisBroker
    nobf_generator: NaughtyOutputBehaviourFeedbackGenerator

    _task_group: TaskGroup | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        """Initialize the command handler and register subscribers."""
        super().__post_init__()

        self.commands: dict[PlayerCommand, Callable[..., Any | Awaitable[Any]]] = {
            "configure_for_experiment": self.configure_for_experiment,
            "forward_pass": self.forward_pass,
            "stop": self.stop_player,
            "reset": self.reset,
            "reflection": self.perform_reflection,
            "send_feedback": self.handle_feedback,
            "get_state": self.get_player_state,
        }

        self.register_subscribers()

    @property
    def command_channel(self) -> str:
        """Get the command channel for this player."""
        return f"player:{self.uuid}:commands"

    def register_subscribers(self) -> None:
        """Register all command subscribers with the broker."""
        for command_name, command_func in self.commands.items():
            channel_name = f"{self.command_channel}:{command_name}"
            _ = self.broker.subscriber(channel_name)(command_func)

    def prepare_prompt_cache(self) -> None:
        """Prepare the prompt cache for the player."""
        paths = Paths()
        manual_paths = KtaneManualPaths()
        PromptCache.initialise(paths.prompts, manual_paths.text_dir, manual_paths.images_small_dir)
        # also load the manual too so that it's cached and ready
        _ = load_manual_as_prompt(image_dimensions=self.capabilities.image_dimensions)

    @asynccontextmanager
    async def lifespan(self) -> AsyncGenerator[None]:
        """Lifespan with task group for background operations."""
        self.prepare_prompt_cache()

        async with anyio.create_task_group() as tg:
            self._task_group = tg
            async with super().lifespan():
                yield

    async def get_player_state(self) -> PlayerState:
        """Get current player state."""
        return self.state

    async def handle_feedback(self, feedback: PlayerMessage[str]) -> bool:
        """Handle feedback message."""
        self.incoming_message_handler.handle_new_message(feedback.message)
        logger.debug("Received feedback", feedback=feedback.message)
        return True

    async def configure_for_experiment(self, data: _ConfigureExperimentPayload) -> bool:
        """Configure the player service for an experiment."""
        if self.state > PlayerState.idle:
            raise HTTPException(
                status_code=500, detail="Player is not ready for experiment configuration."
            )
        self.state = PlayerState.configuring_experiment

        logger.info(
            "Set state to configuring experiment", service_name=self.service_name, state=self.state
        )

        self.protocol = data.protocol
        self.experiment_descriptor = data.experiment_descriptor

        await self.experiment_recorder.configure_for_experiment(
            experiment_descriptor=self.experiment_descriptor,
            protocol=self.protocol,
            player_uuid=self.uuid,
        )

        self.message_history = MessageHistory(
            capabilities=self.capabilities, protocol=self.protocol
        )
        self.input_builder = AgentInputBuilder(
            capabilities=self.capabilities,
            protocol=self.protocol,
            observation_handler=self.observation_handler,
            recorder=self.experiment_recorder,
        )

        self.action_predictor.configure_for_experiment(
            protocol=self.protocol, message_history=self.message_history
        )
        self.action_dispatcher.configure_for_experiment(
            protocol=self.protocol, experiment_descriptor=self.experiment_descriptor
        )

        if self.protocol.role == "defuser":
            self.game_client.game_uuid = self.experiment_descriptor.game_uuid
            await self.game_client.start()

        await self.incoming_message_handler.start_subscriber()

        self.state = PlayerState.waiting_for_turn
        logger.info("Configured player for experiment", protocol=self.protocol, state=self.state)
        return True

    async def forward_pass(self) -> dict[str, Any]:
        """Perform a forward pass for the player."""
        if self.state != PlayerState.waiting_for_turn:
            raise HTTPException(status_code=503, detail="Player is not ready for a forward pass.")

        logger.debug(f"Step {self.experiment_recorder.num_steps}")

        # Collect the state and the observations
        if self.protocol.role == "defuser":
            self.state = PlayerState.waiting_for_observation
            bomb_state, raw_frames = await self.game_client.get_observation()
        else:
            bomb_state, raw_frames = None, None

        self.state = PlayerState.pulling_messages
        messages = self.incoming_message_handler.pull_messages()

        # Prepare the input
        self.state = PlayerState.preparing_agent_input
        agent_input = await self.input_builder.build_agent_input(
            messages=messages,
            raw_frames=raw_frames,
            bomb_state=bomb_state,
            is_message_history_empty=self.message_history.is_empty,
        )

        # Decide what action to do
        self.state = PlayerState.waiting_for_action
        agent_call_result = await self.action_predictor.send_request_to_agent(
            message_input=agent_input
        )

        # Perform the action
        self.state = PlayerState.performing_action
        agent_call_result = await self.action_dispatcher.direct_output_from_agent(
            agent_call_result
        )

        # TODO: Provide call result to feedback handlers
        _ = await self.generate_feedbacks(agent_call_result)

        await self.update_metrics(agent_call_result)

        # Return to a waiting for turn state
        self.state = PlayerState.waiting_for_turn

        return {"success": True, "state": self.state.name}

    async def generate_feedbacks(self, agent_call_result: AgentCallResult[Any]) -> None:
        """Generate feedbacks based on the agent call result."""
        nobf_output = self.nobf_generator.generate(agent_call_result=agent_call_result)

        if nobf_output:
            _ = await self.handle_feedback(PlayerMessage(message=nobf_output))

        # # TODO: if we have tapf enabled, generate tapf
        # tapf_output = self.tapf_generator.generate(all_bomb_states=self.experiment_recorder)
        # if tapf_output:
        #     _ = await self.handle_feedback(tapf_output)

    async def update_metrics(
        self, agent_call_result: AgentCallResult[PlayerOutputType | KtaneGameplayInput]
    ) -> None:
        """Update the metrics for the player based on the agent call result."""
        self.message_history.update(
            new_messages=agent_call_result.new_messages, usage=agent_call_result.usage
        )

        self.experiment_recorder.track_step(
            agent_call_result=agent_call_result,
            num_prompt_truncations=self.message_history.num_times_truncated,
            is_reflection=False,
        )

    async def perform_reflection(self, message: PlayerMessage[str]) -> bool:
        """Perform a reflection for the player."""
        if self.state != PlayerState.waiting_for_turn:
            raise HTTPException(
                status_code=503,
                detail=f"Player is not ready for a reflection. They are: {self.state.name}",
            )

        self.state = PlayerState.reflecting
        agent_call_result = await self.action_predictor.send_reflection_request(
            reflection_message=message.message
        )

        self.experiment_recorder.track_step(
            agent_call_result=agent_call_result,
            num_prompt_truncations=self.message_history.num_times_truncated,
            is_reflection=True,
        )

        self.state = PlayerState.waiting_for_turn
        return True

    @logfire.instrument("Stop player")
    async def stop_player(self, stop_event: StopPlayerEvent) -> dict[str, str]:
        """Stop the player and end the experiment.

        We respond quickly with a 202 and let this run in the background because export/wandb can
        block and take a while to finish. The tracker will already run in a background thread but
        we don't want to block API calls while waiting for the experiment to finish.

        This is less important in context of an experiment since the heartbeats are done completely
        separately by a supervisor, but it is still a good practice to not block the API.
        """
        if self.state >= PlayerState.stopping:
            return {"status": "accepted", "reason": "Player is already stopping or stopped."}

        self.state = PlayerState.stopping
        logger.info("Stopping player and ending experiment")
        # Force a heartbeat update to let the EM know we are stopping because if not, this can
        # literally move incredibly quickly and hit the reset() before the EM notices, which causes
        # errors.
        await self.send_heartbeat()

        # Spawn background task for cleanup
        if self._task_group:
            self._task_group.start_soon(self._stop_player_async, stop_event)

        return {"status": "accepted", "reason": "Stopping player and ending experiment"}

    async def _stop_player_async(self, stop_event: StopPlayerEvent) -> None:
        """Async cleanup task for stopping player."""
        if not hasattr(self, "protocol"):
            logger.error("Can't stop player, player was not setup properly")
            self.reset()
            return

        # Add the final bomb state for the defuser
        if self.protocol.role == "defuser" and stop_event.bomb_state:
            self.experiment_recorder.add_final_bomb_state(final_bomb_state=stop_event.bomb_state)
        # Stop the experiment tracking
        self.state = PlayerState.uploading
        await self.experiment_recorder.on_experiment_stop(is_hard_crash=stop_event.hard_crash)

        await self.incoming_message_handler.stop_subscriber()
        # Reset the state
        self.reset()
