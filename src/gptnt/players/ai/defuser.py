import abc
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Union, override

import logfire
import structlog
import whenever
from pydantic_ai import BinaryContent

from gptnt.common.async_ops import busy_wait_interval
from gptnt.common.paths import Paths
from gptnt.ktane.client import KtaneClient
from gptnt.ktane.state.game import GameState
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
    observation_window_length: int = 1
    should_save_images: bool = False

    def __post_init__(self) -> None:
        """Post init for the defuser player."""
        self.observation_cache: deque[BinaryContent] = deque(maxlen=self.observation_window_length)

    @override
    async def connect(self) -> None:
        await super().connect()
        _ = await self.game_client.__aenter__()

    @override
    async def disconnect_from_room(self) -> None:
        await super().disconnect_from_room()
        _ = await self.game_client.__aexit__()

    @override
    async def health_check(self) -> None:
        await super().health_check()
        assert await self.game_client.healthcheck() in {GameState.lights_on, GameState.lights_off}

    @logfire.instrument("Send action to the game")
    async def send_action_to_game(self, action: InteractGameAction[LocationDataT]) -> None:
        """Send an action to the game client."""
        # TODO: handle the return from the game client
        bomb_state = await self.game_client.send_action(action)
        self.tracker.add_action(action=action)
        if bomb_state is not None:  # This *should* always be true
            self.tracker.add_bomb_state(bomb_state=bomb_state)

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

        messages = await self.pull_unread_messages_from_dialogue_space()
        # Frame is/should be a JPEG that is encoded as bytes
        raw_image, segm_mask, som_image = await self.game_client.get_observation()
        self.tracker.add_observation(raw_image=raw_image, segm_mask=segm_mask, som_image=som_image)
        current_frame = BinaryContent(data=som_image, media_type="image/png")

        self.observation_cache.append(current_frame)

        if self.should_save_images:
            paths.output.joinpath("images").mkdir(parents=True, exist_ok=True)
            _ = (
                paths.output.joinpath("images")
                .joinpath(f"frame_{whenever.Instant.now()}.png")
                .write_bytes(current_frame.data)
            )

        agent_input = [messages, *list(self.observation_cache)]
        return agent_input

    @override
    def build_deps_for_request(self) -> None:
        """Return None since this class doesn't use tools or deps."""
        return  # noqa: WPS324
