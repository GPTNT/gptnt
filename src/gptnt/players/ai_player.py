from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import override

import logfire
import structlog
from pydantic import ValidationError
from pydantic_ai import Agent
from pydantic_ai.exceptions import AgentRunError, ModelHTTPError
from pydantic_ai.messages import BinaryContent
from pydantic_ai.models import Model

from gptnt.api.commands import ReflectionCommand
from gptnt.api.experiment_manager.experiment_descriptor import ExperimentDescriptor
from gptnt.common.instrumentation import InstrumentationDataclassMixin
from gptnt.players.actions import (
    DoNothingAction,
    InteractGameAction,
    InteractGameActionType,
    PlayerOutputType,
    SendMessageAction,
)
from gptnt.players.base_player import BasePlayer
from gptnt.players.messages import AgentMessageInput, MessageHistory
from gptnt.players.metrics.episode_tracker import EpisodeTracker
from gptnt.players.observations import ObservationHandler
from gptnt.players.output_validators import (
    AgentOutput,
    InvalidOutputFormatError,
    structure_string_output,
)
from gptnt.players.prompts import (
    load_instructions_deps,
    load_manual_as_prompt,
    load_reflection_prompt,
)
from gptnt.players.spec import PlayerDeps, PlayerMetadata, PlayerSpec

log = structlog.get_logger()


@dataclass(kw_only=True)
class AIPlayer(BasePlayer, InstrumentationDataclassMixin):
    """An AI Player.

    This will have everything that the AI player needs to run or anything.
    """

    agent: Agent[PlayerDeps | None, PlayerOutputType | str]
    """The PydanticAI agent that the AI player uses."""

    metadata: PlayerMetadata
    tracker: EpisodeTracker

    observation_handler: ObservationHandler

    player_spec: PlayerSpec = field(init=False, repr=False)
    message_history: MessageHistory = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Prepare agent."""
        super().__post_init__()

        # Setup the tracker
        self.tracker.player_uuid = self.uuid

        # Setup the agent
        self.agent._deps_type = PlayerDeps  # noqa: SLF001
        _ = self.agent.instructions(load_instructions_deps)

    @override
    def perform_instrumentation(self) -> None:
        log.debug("Instrumenting AI player.")
        logfire.instrument_pydantic_ai(self.agent)  # pyright: ignore[reportCallIssue, reportArgumentType]

    @property
    def model_name(self) -> str:
        """Get the name of the model."""
        if isinstance(self.agent.model, str):
            return self.agent.model
        if isinstance(self.agent.model, Model):
            return self.agent.model.model_name
        raise ValueError("Model name not found")

    @override
    @logfire.instrument("Start experiment")
    async def on_experiment_start(
        self, *, experiment_descriptor: ExperimentDescriptor, spec: PlayerSpec
    ) -> None:
        """Things to do when the experiment starts."""
        self.player_spec = spec
        self.message_history = MessageHistory(metadata=self.metadata, spec=self.player_spec)
        await self.tracker.on_experiment_start(
            experiment_descriptor=experiment_descriptor,
            player_spec=self.player_spec,
            additional_metadata={},
        )
        log.info("Starting experiment", spec=self.player_spec, metadata=self.metadata)

    @override
    @logfire.instrument("Stop experiment")
    async def on_experiment_stop(self, *, is_hard_crash: bool = False) -> None:
        """Things to do when the experiment stops."""
        log.info("Stopping experiment")
        self.tracker.num_prompt_truncations = self.message_history.num_times_truncated
        await self.tracker.on_experiment_stop(is_hard_crash=is_hard_crash)

    @override
    async def lifespan_setup(self) -> None:
        """Asynchronous logic to run after app startup."""
        await super().lifespan_setup()
        with logfire.span("Start AI player"):
            log.info(f"Start Player with UUID: {self.uuid}", metadata=self.metadata)
            _ = self.background_tasks.create_task(self.ready())

    @override
    @logfire.instrument("Cleanup AI player")
    async def lifespan_cleanup(self) -> None:
        """Asynchronous logic to run during app shutdown."""
        log.info(f"Stop Player with UUID: {self.uuid}", metadata=self.metadata)

    @override
    @logfire.instrument("Handle reflection")
    async def handle_reflection_message(self, reflection_command: ReflectionCommand) -> None:
        reflection_prompt = load_reflection_prompt()

        log.info(
            f"Handling a reflection message, got case: {reflection_command.reflection_message}"
        )

        response = await self.agent.run(
            [reflection_command.reflection_message, reflection_prompt],
            deps=self._agent_deps,
            output_type=str,
            message_history=self.message_history.to_history(),
        )
        response_as_action = SendMessageAction(message=response.output)

        self.tracker.add_reflection(message=response_as_action, role=self.player_spec.role)

    @override
    @logfire.instrument("Run forward pass")
    async def forward_pass(self) -> None:
        """Perform a single forward pass of the AI player."""
        agent_input = await self.build_agent_input()
        agent_output = await self.send_request_to_agent(message_input=agent_input)
        await self._direct_output_from_agent(agent_output.output)
        self.tracker.num_requests += 1
        self.tracker.step()

    @logfire.instrument("Build agent input")
    async def build_agent_input(self) -> AgentMessageInput:
        """Build the input for the agent."""
        agent_input = []

        # 1. Do we want to include the manual? Only if first message and we want it.
        if self.player_spec.include_manual and self.message_history.is_empty:
            agent_input.extend(load_manual_as_prompt())

        # 2. Pull messages. This should only happen if we are not playing alone, AND this is not
        #    the first message.
        if not self.player_spec.is_playing_alone and not self.message_history.is_empty:
            messages = await self.pull_messages()
            agent_input.append(messages)

        # 3. Add observations if we are the defuser
        if self.player_spec.role == "defuser":
            observations = await self._prepare_frames()
            agent_input.extend(observations)

        return agent_input

    @logfire.instrument("Send request to agent")
    async def send_request_to_agent(self, *, message_input: AgentMessageInput) -> AgentOutput:
        """Send a message to the AI.

        This will be the main way to send messages to the AI.
        """
        self.message_history.truncate_history_if_needed()
        # self.tracker.start_weave_trace(message_input, self.message_history.to_history())
        try:  # noqa: WPS229
            model_output = await self.agent.run(
                message_input,
                deps=self._agent_deps,
                output_type=self._agent_deps.output_type,
                message_history=self.message_history.to_history(),
            )
            model_output.output = structure_string_output(
                output=model_output.output, output_type=self._agent_deps.structured_output_type
            )
        except InvalidOutputFormatError as format_error:
            log.exception(
                "Invalid output format from the agent.",
                error=format_error,
                message_input=message_input,
            )
            self.tracker.num_invalid_formats += 1
            return AgentOutput.do_nothing()
        except ValidationError as validation_error:
            log.exception(
                "Validation error from the agent.",
                error=validation_error,
                message_input=message_input,
            )
            self.tracker.num_invalid_formats += 1
            return AgentOutput.do_nothing()
        except (ModelHTTPError, AgentRunError) as err:
            if "filtered due to the prompt triggering Azure OpenAI's content" in err.message:
                log.exception("Filtered due to content policy", error=err)
                self.tracker.guardrail_violations += 1
            else:
                log.exception("Something has gone wrong, defaulting to `DoNothing`", error=err)
            return AgentOutput.do_nothing()

        # It should not be a string, like if its a string I will be very surprised because we are
        # using the output validator
        assert not isinstance(model_output.output, str)

        self.message_history.update(
            new_messages=model_output.new_messages(), usage=model_output.usage()
        )
        # self.tracker.finish_weave_trace(model_output.output, model_output.usage())

        return AgentOutput.with_message_cleanup(
            output=model_output.output,
            usage=model_output.usage(),
            new_messages=model_output.new_messages(),
        )

    def agent_output_type_to_function(
        self, output_type: type[PlayerOutputType]
    ) -> Callable[[PlayerOutputType], Awaitable[None]]:
        """Map the output type from the AI model to a method within the function.

        This will allow us to dynamically convert the output from the AI model to a function that
        can be called to carry the logic forwards.
        """
        if issubclass(output_type, InteractGameAction):
            output_type = InteractGameAction

        switcher: dict[type[PlayerOutputType], Callable[..., Awaitable[None]]] = {
            SendMessageAction: self._send_message,
            DoNothingAction: self._do_nothing_action,
            InteractGameAction: self.send_game_action,
        }
        return switcher[output_type]

    @override
    async def send_game_action(self, action: InteractGameActionType) -> None:
        """Send a game action to the game."""
        self.tracker.add_action(action=action)
        game_action = self.observation_handler.convert_to_game_action(action=action)
        return await super().send_game_action(action=game_action)

    @logfire.instrument("Prepare frames")
    async def _prepare_frames(self) -> list[BinaryContent]:
        """Prepare frames from the game."""
        pulled_observations = await self.pull_observation()
        if not pulled_observations:
            raise ValueError("No observations pulled from the game.")

        bomb_state = pulled_observations.bomb_state

        observation = self.observation_handler.handle_new_observtion(
            frames=pulled_observations.observation_frames.frames,
            segmentation=pulled_observations.observation_frames.segm_mask,
            bomb_state=pulled_observations.bomb_state,
        )
        self.tracker.add_observation(
            frames=observation.frames,
            segm_mask=observation.segm_mask,
            som_image=observation.som_image,
        )
        self.tracker.add_bomb_state(bomb_state=bomb_state)

        # TODO: save the frames to disk?

        # 3. Figure out how many frames we need to send
        num_frames_to_use = (
            self.metadata.max_observation_window_length
            if bomb_state.view_needs_multiple_frames
            else 1
        )

        # 4. Build the observations
        observations = [
            *[
                BinaryContent(data=frame, media_type="image/png")
                # Get the last `num_frames_to_use` frames, but not the last one in the list since
                # we want to replace it with the SoM image
                for frame in observation.frames[-num_frames_to_use:-1]
            ],
            BinaryContent(data=observation.som_image, media_type="image/png"),
        ]
        return observations

    @property
    def _agent_deps(self) -> PlayerDeps:
        """Get the agent dependencies."""
        return PlayerDeps(spec=self.player_spec, metadata=self.metadata)

    async def _direct_output_from_agent(self, agent_output: PlayerOutputType) -> None:
        """Process output from Agent and direct to correct function.

        Once it comes in, index the type in the agent_output_type_to_function and call the function
        that is mapped to that type. This will allow us to dynamically convert the result from the
        AI model to a function that can be called to carry the logic forwards.
        """
        method = self.agent_output_type_to_function(type(agent_output))
        return await method(agent_output)

    async def _send_message(self, action: SendMessageAction) -> None:
        """Send a message to the dialogue space."""
        self.tracker.add_message(message=action, role=self.player_spec.role)
        return await self.send_dialogue_message(action.message)

    async def _do_nothing_action(self, action: DoNothingAction) -> None:
        """Do nothing action."""
        self.tracker.add_do_nothing(action, role=self.player_spec.role)
