import abc
import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Union, override

import logfire
import structlog
import whenever
from pydantic import TypeAdapter, ValidationError
from pydantic_ai import BinaryContent

from gptnt.api.structures import GameMetadata
from gptnt.common.async_ops import busy_wait_interval
from gptnt.common.paths import Paths
from gptnt.ktane.client import KtaneClient
from gptnt.players.actions import (
    DoNothingAction,
    InteractGameAction,
    InteractGameLocation,
    SendMessageAction,
)
from gptnt.players.ai.ai_player import AIPlayer, set_model_output
from gptnt.players.metrics.structures import AdditionalEndGameMetrics
from gptnt.processors.set_of_marks import InvalidMarkLocationError

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
    max_observation_window_length: int = 12
    should_save_images: bool = False

    sequential_step_time: float = 3
    """How long to run the game for before stopping time again in sequential mode."""

    current_observation_window_length: int = 1
    """Current observation window length."""

    @override
    def coerce_model_string_outputs(self, output: str) -> DefuserOutputT[LocationDataT]:
        output = output.strip().replace("```json", "").replace("```", "")
        try:
            return TypeAdapter(DefuserOutputT[InteractGameLocation]).validate_json(output)
        except ValidationError:
            log.warning('Trying with the `"}` on the end', output=output)
            return TypeAdapter(DefuserOutputT[InteractGameLocation]).validate_json(output + '"}')  # noqa: WPS336

    @override
    async def disconnect_from_room(self) -> None:
        await super().disconnect_from_room()
        _ = await self.game_client.__aexit__()

    @override
    async def on_experiment_start(
        self, *, game_metadata: GameMetadata, additional_metadata: dict[str, Any] | None = None
    ) -> None:
        """Things to do when the experiment starts."""
        # Check for number of observations
        should_use_bigger_window = game_metadata.requires_multiple_images_per_observation
        self.current_observation_window_length = (
            self.max_observation_window_length if should_use_bigger_window else 1
        )
        log.debug(
            f"Setting observation window length (to={self.current_observation_window_length})"
        )

        self.player_usage.num_images_per_message = self.current_observation_window_length

        await super().on_experiment_start(
            game_metadata=game_metadata, additional_metadata=additional_metadata
        )

    @override
    async def on_experiment_stop(
        self, *, additional_end_game_metrics: AdditionalEndGameMetrics | None = None
    ) -> None:
        log.debug("Getting last bomb state")
        last_bomb_state = await self.game_client.get_state()
        if last_bomb_state is not None:
            self.tracker.add_bomb_state(last_bomb_state)
        await super().on_experiment_stop(additional_end_game_metrics=additional_end_game_metrics)

    @logfire.instrument("Send action to the game")
    async def send_action_to_game(self, action: InteractGameAction[LocationDataT]) -> None:
        """Send an action to the game client."""
        try:
            _ = await self.game_client.send_action(action)
        except InvalidMarkLocationError:
            log.exception("SoM failed, replacing with `DoNothing` action", action=action)
            action = DoNothingAction()  # pyright: ignore[reportAssignmentType]
            # Update the last message in the history to reflect that nothing happened
            self.player_usage.message_history[-1] = set_model_output(
                messages=self.player_usage.message_history[-1],
                return_content_as_json=action.model_dump_json(),
            )
            self.tracker.num_invalid_locations += 1

        self.tracker.add_action(action=action)

    @override
    async def run_sequential(self) -> None:  # noqa: WPS217
        """Run the decision making process for the player once."""
        while await self.game_client.get_state() is None:
            await busy_wait_interval()

        agent_output = await self.send_request_to_agent()
        _ = await self.direct_output_from_agent(agent_output)
        _ = await self.game_client.advance_time()
        await asyncio.sleep(self.sequential_step_time)

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

        num_frames_to_use = (
            self.max_observation_window_length
            if state is not None and state.view_needs_multiple_frames
            else 1
        )

        self.tracker.add_observation(
            frames=frames[-num_frames_to_use:], segm_mask=segm_mask, som_image=som_image
        )

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
        observations = [*current_frames[:-1], som_frame][-self.current_observation_window_length :]

        agent_input = [messages, *observations]
        return agent_input

    @override
    def build_deps_for_request(self) -> None:
        """Return None since this class doesn't use tools or deps."""
        return  # noqa: WPS324
