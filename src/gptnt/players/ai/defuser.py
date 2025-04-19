import abc
from collections import deque
from collections.abc import Awaitable, Callable
from typing import Union, override

import structlog
from pydantic_ai import Agent, BinaryContent

from gptnt.dialogue_space.client import DialogueSpaceClient
from gptnt.ktane.client import KtaneClient
from gptnt.players.actions import (
    DoNothingAction,
    InteractGameAction,
    InteractGameLocation,
    SendMessageAction,
)
from gptnt.players.ai.ai_player import AIPlayer

log = structlog.get_logger()


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

    role = "defuser"

    def __init__(
        self,
        agent: Agent[AgentDepsT, DefuserOutputT[LocationDataT]],
        dialogue_space_client: DialogueSpaceClient,
        game_client: KtaneClient,
        *,
        observation_window_length: int = 1,
    ) -> None:
        super().__init__(agent, dialogue_space_client)
        self.game_client = game_client

        self.observation_cache: deque[BinaryContent] = deque(maxlen=observation_window_length)

    @override
    async def connect(self) -> None:
        await super().connect()
        _ = await self.game_client.__aenter__()

    @override
    async def health_check(self) -> None:
        await super().health_check()
        assert await self.game_client.healthcheck() is True

    async def send_action_to_game(self, action: InteractGameAction[LocationDataT]) -> None:
        """Send an action to the game client."""
        # TODO: handle the return from the game client
        _ = await self.game_client.send_action(action)

        raise NotImplementedError

    @override
    def agent_output_type_to_function(
        self, output_type: type[DefuserOutputT[LocationDataT]]
    ) -> Callable[[DefuserOutputT[LocationDataT]], Awaitable[None]]:
        switcher: dict[type[DefuserOutputT[LocationDataT]], Callable[..., Awaitable[None]]] = {
            SendMessageAction: self.send_message_to_dialogue_space,
            DoNothingAction: self.do_nothing_action,
            InteractGameAction[LocationDataT]: self.send_action_to_game,
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
    async def build_agent_input(self) -> list[str | BinaryContent]:
        """Build the input for the defuser."""
        messages = await self.pull_unread_messages_from_dialogue_space()
        # Frame is/should be a JPEG that is encoded as bytes
        current_frame = BinaryContent(
            await self.game_client.get_observation(), media_type="image/png"
        )

        self.observation_cache.append(current_frame)

        agent_input = [messages, *list(self.observation_cache)]
        return agent_input

    @override
    def build_deps_for_request(self) -> None:
        """Return None since this class doesn't use tools or deps."""
        return  # noqa: WPS324
