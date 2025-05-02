import abc
import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Union, override

import logfire
import structlog
import whenever
from pydantic import TypeAdapter, ValidationError
from pydantic_ai import Agent, BinaryContent
from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart
from pydantic_ai.models import Model

from gptnt.common.async_ops import busy_wait_interval
from gptnt.common.paths import Paths
from gptnt.ktane.client import KtaneClient
from gptnt.players.actions import (
    DoNothingAction,
    InteractGameAction,
    InteractGameLocation,
    SendMessageAction,
)
from gptnt.players.ai.ai_player import AIPlayer

log = structlog.get_logger()

paths = Paths()

type DefuserOutputT[LocationDataT: InteractGameLocation] = Union[  # noqa: UP007
    DoNothingAction, SendMessageAction, InteractGameAction[LocationDataT]
]
"""Result type for the defuser player.

It's a generic as the location data type must be specified on player instantiation. This allows us
to automatically switch between set-of-marks, relative coordinates, or however else we decide to
choose locations to act in the environment.

Note: Needs to be Union until PEP-747 lands.
https://ai.pydantic.dev/results/#structured-result-validation
"""


def coerce_model_string_outputs(output: str) -> DefuserOutputT[InteractGameLocation]:
    """Parse the output from the agent for gemini/models that don't support structured output."""
    output = output.strip().replace("```json", "").replace("```", "")
    return TypeAdapter(DefuserOutputT[InteractGameLocation]).validate_json(output)


def does_model_support_structured_outputs(agent: Agent[Any, Any]) -> bool:
    """Check if the model supports structured outputs."""
    if isinstance(agent.model, str):
        model_name_string = agent.model
    elif isinstance(agent.model, Model):
        model_name_string = agent.model.model_name
    else:
        raise TypeError("Cannot determine model name from agent")

    return "gemini" not in model_name_string


def remove_binary_content_from_user_message(message: ModelMessage) -> ModelMessage:
    """Remove binary content from the message."""
    if isinstance(message, ModelRequest):
        for part in message.parts:
            # Check if its a thing we need to remove binary content from
            if isinstance(part, UserPromptPart) and isinstance(part.content, list):
                part.content = [
                    piece for piece in part.content if not isinstance(piece, BinaryContent)
                ]
    return message


@dataclass(kw_only=True)
class BaseDefuserPlayer[AgentDepsT, LocationDataT: InteractGameLocation](
    AIPlayer[AgentDepsT, DefuserOutputT[LocationDataT]], abc.ABC
):
    """Base defuser player for the game.

    We are using a base class to allow for different implementations of the defuser player. This
    can allow for future experiments with different ways of interacting with the game, such as
    using function tools.

    LocationDataT is a generic that should be set to the location data type that the game client
    uses to represent locations in the game.

    By default, all observations are stored in a deque with a max length of 1. This means that we
    can easily support windowed or MDP-style defuser players.
    """

    game_client: KtaneClient
    observation_window_length: int = 12
    should_save_images: bool = False

    sequential_step_time: float = 3
    """How long to run the game for before stopping time again in sequential mode."""

    def __post_init__(self) -> None:
        """Post init for the defuser player."""
        super().__post_init__()
        if not does_model_support_structured_outputs(self.agent):
            self.agent.output_validator(coerce_model_string_outputs)  # pyright: ignore[reportArgumentType,reportCallIssue]

    @override
    async def connect(self) -> None:
        await super().connect()
        _ = await self.game_client.__aenter__()

    @override
    async def disconnect_from_room(self) -> None:
        await super().disconnect_from_room()
        _ = await self.game_client.__aexit__()

    @override
    async def on_experiment_stop(self) -> None:
        log.debug("Getting last bomb state")
        last_bomb_state = await self.game_client.get_state()
        if last_bomb_state is not None:
            self.tracker.add_bomb_state(last_bomb_state)

        await super().on_experiment_stop()

    @logfire.instrument("Send action to the game")
    async def send_action_to_game(self, action: InteractGameAction[LocationDataT]) -> None:
        """Send an action to the game client."""
        _ = await self.game_client.send_action(action)
        self.tracker.add_action(action=action)

    @override
    async def run_sequential(self) -> None:  # noqa: WPS217
        """Run the decision making process for the player once."""
        while await self.game_client.get_state() is None:
            await busy_wait_interval()

        agent_output = await self.send_request_to_agent()
        if isinstance(agent_output, InteractGameAction):
            _ = await self.direct_output_from_agent(agent_output)
        await asyncio.sleep(self.sequential_step_time)
        _ = await self.game_client.advance_time()

    @override
    @logfire.instrument("Map agent output to function", record_return=True)
    def agent_output_type_to_function(
        self, output_type: type[DefuserOutputT[LocationDataT]]
    ) -> Callable[[DefuserOutputT[LocationDataT]], Awaitable[None]]:
        if issubclass(output_type, InteractGameAction):
            output_type = InteractGameAction

        switcher: dict[type[DefuserOutputT[LocationDataT]], Callable[..., Awaitable[None]]] = {
            SendMessageAction: self.send_message_to_dialogue_space,
            DoNothingAction: self.do_nothing_action,
            InteractGameAction: self.send_action_to_game,
        }
        return switcher[output_type]

    @override
    def add_new_messages_to_history(self, messages: list[ModelMessage]) -> None:
        """Add new messages to the message history.

        This removes any observations from the messages before adding them to the history.
        """
        messages_to_add = [
            remove_binary_content_from_user_message(message)
            if isinstance(message, ModelRequest)
            else message
            for message in messages
        ]
        self._message_history.extend(messages_to_add)

    @override
    async def send_request_to_agent(self) -> DefuserOutputT[LocationDataT]:
        """Send a request to the agent and coerce the output if we need to.

        Just super() from the parent class and then coerce the output to the correct type because
        we can't trust Gemini.
        """
        agent_output = await super().send_request_to_agent()
        if isinstance(agent_output, str):
            try:
                agent_output = coerce_model_string_outputs(agent_output)
            except ValidationError:
                log.exception(
                    "Failed to coerce model output; returning `DoNothingAction`",
                    agent_output=agent_output,
                )
                agent_output = DoNothingAction()

        # The return type should be fine but pyright doesn't like it because I'm using a lot of
        # generics everything and I think it's getting confused
        return agent_output  # pyright: ignore[reportReturnType]


class MDPDefuserPlayer[LocationDataT: InteractGameLocation](
    BaseDefuserPlayer[None, LocationDataT]
):
    """MDP-style Defuser player.

    This implements the defuser in a "MDP"-style, meaning that each input to the agent is
    accompanied by an observation from the environment.

    LocationDataT is a generic that should be set to the location data type that the game client
    uses to represent locations in the game.
    """

    @override
    @logfire.instrument("Build agent input")
    async def build_agent_input(self) -> list[str | BinaryContent]:
        """Build the input for the defuser."""
        # Wait for a valid bomb state (lights on) before receiving any observations
        while await self.game_client.get_state() is None:
            await busy_wait_interval()

        # Store the bomb state in the tracker
        state = await self.game_client.get_state()
        if state is not None:
            self.tracker.add_bomb_state(state)

        # Get the messages from the dialogue space
        messages = await self.pull_unread_messages_from_dialogue_space()

        # Frame is/should be a PNG that is encoded as bytes
        frames, segm_mask, som_image = await self.game_client.get_observation_frames()
        self.tracker.add_observation(frames=frames, segm_mask=segm_mask, som_image=som_image)

        if self.should_save_images:
            paths.output.joinpath("images").mkdir(parents=True, exist_ok=True)
            _ = (
                paths.output.joinpath("images")
                .joinpath(f"frame_{whenever.Instant.now()}.png")
                .write_bytes(som_image)
            )

        som_frame = BinaryContent(data=som_image, media_type="image/png")
        current_frames = [BinaryContent(data=frame, media_type="image/png") for frame in frames]

        # Build the observations by getting all the frames and replacing the last one with the SoM
        # frame. Then, we take the last N frames to build the observation window
        observations = [*current_frames[:-1], som_frame][-self.observation_window_length :]

        agent_input = [messages, *observations]
        return agent_input

    @override
    def build_deps_for_request(self) -> None:
        """Return None since this class doesn't use tools or deps."""
        return  # noqa: WPS324
