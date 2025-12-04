from typing import Literal, Self, Union, cast

from pydantic import BaseModel, Field
from pydantic.fields import computed_field
from pydantic.functional_validators import model_validator
from pydantic_ai.usage import UsageLimits

from gptnt.common.image_ops import ImageDimensions
from gptnt.players.actions import (
    DoNothingAction,
    DoNothingActionWithThoughts,
    InteractGameAction,
    InteractGameActionWithThoughts,
    MagicGameAction,
    PlayerOutputType,
    SendMessageAction,
    SendMessageActionWithThoughts,
    SingleAlphabetLetter,
)

type PlayerType = Literal["ai", "human"]
type PlayerRole = Literal["defuser", "expert"]
type ThinkingFramework = Literal["act", "react", "redact", "dreact"]
type CommunicationStyle = Literal["async", "sync"]


class PlayerCapabilities(BaseModel, frozen=True):
    """The capabilities of a player, that is set once on instantiation.

    This tells the EM what the player is and what they can do for the matchmaking.
    """

    player_name: str
    """The name of the player."""

    player_type: PlayerType
    """The type of player (AI or human)."""

    supports_structured_output: bool
    """Whether the player supports structured output."""

    max_observation_window_length: int = 16
    """The maximum observation window length for the player.

    We default this to 16.
    """
    usage_limits: UsageLimits = Field(default_factory=UsageLimits)

    desired_image_dimensions: ImageDimensions | None = None
    """The desired input image dimensions for the player."""


class PlayerProtocol(BaseModel, frozen=True):
    """Protocol that a player has for some given experiment."""

    role: PlayerRole
    """The role of the player in the experiment.

    This also determines what they will have access to.
    """

    communication_style: CommunicationStyle
    """The style of communication the player will use.

    Either async (all players communicate at once) or sync (players take turns).
    """

    is_playing_alone: bool
    """Whether the player is playing alone or with others."""

    include_manual: bool
    """Whether the manual should be included in the prompt."""

    thinking_framework: ThinkingFramework
    """The thinking framework the player will use.

    While this not a necessary field to have, it is useful to allow for easily converting the
    combination of the below options into a single string.
    """

    allow_thoughts_output: bool
    """Whether to allow the players to include thoughts."""

    allow_thoughts_in_history: bool
    """Whether the player's own thoughts should be included in histories for future turns."""

    allow_outputs_in_history: bool
    """Whether the player's own outputs should be included in histories for future turns."""

    receive_feedback_after_action: bool = False
    """Whether or not a player should receive feedback after each action."""

    allow_magic_actions: bool = False

    @property
    def output_type(self) -> type[PlayerOutputType]:
        """The output type for the player.

        This is used to determine what the agent can output.

        Note that at the end, we also patch the name so that it can be used by various tool
        functions because for some reason, this was not working properly. That said, doing this and
        using structured outputs is risky until PydanticAI is a bit more stable?
        """
        # Always allow do nothing
        output: list[type[PlayerOutputType]] = []

        if self.allow_thoughts_output:
            output.append(DoNothingActionWithThoughts)
        else:
            output.append(DoNothingAction)

        if not self.is_playing_alone:
            if self.allow_thoughts_output:
                output.append(SendMessageActionWithThoughts)
            else:
                output.append(SendMessageAction)

        if self.role == "defuser":
            if self.allow_thoughts_output:
                output.append(InteractGameActionWithThoughts[SingleAlphabetLetter])
            else:
                output.append(InteractGameAction[SingleAlphabetLetter])

        if self.allow_magic_actions:
            output.append(MagicGameAction)

        clean_output: list[type[PlayerOutputType]] = []
        for output_type in output:
            # Remove the brackets from the output type name
            output_type.__name__ = output_type.__name__.replace("[", "").replace("]", "")
            output_type.__qualname__ = output_type.__qualname__.replace("[", "").replace("]", "")
            clean_output.append(output_type)

        return cast("type[PlayerOutputType]", Union[tuple(clean_output)])  # noqa: UP007

    @property
    def is_solo_player(self) -> bool:
        """Whether the player is a solo player.

        This is used to determine whether the player is playing alone or with others.
        """
        return self.is_playing_alone and self.role == "defuser"

    @computed_field
    @property
    def allow_message_output(self) -> bool:
        """Whether to allow the players to send messages to each other.

        This only makes sense if the player is not playing alone.
        """
        # * Note: the expert should always be able to send messages since that is their point.
        return not self.is_playing_alone

    @model_validator(mode="after")
    def check_expert_is_not_playing_alone(self) -> Self:
        """An expert cannot play alone.

        It doesn't make sense for them to be alone.
        """
        if self.role == "expert" and self.is_playing_alone:
            raise ValueError("An expert cannot play alone.")
        return self

    @model_validator(mode="after")
    def check_thoughts_in_history_without_thoughts(self) -> Self:
        """It doesn't make sense to have thoughts in history if we don't allow thoughts."""
        if self.allow_thoughts_in_history and not self.allow_thoughts_output:
            raise ValueError(
                "It doesn't make sense to have thoughts in history if we don't allow thoughts."
            )
        return self


class PlayerDeps(BaseModel, frozen=True):
    """Dependencies for the AI player (as in PydanticAI)."""

    capabilities: PlayerCapabilities
    protocol: PlayerProtocol

    @property
    def output_type(self) -> type[PlayerOutputType] | type[str]:
        """The output type for the player.

        This is used to determine what the agent can output.
        """
        return self.structured_output_type if self.capabilities.supports_structured_output else str

    @property
    def structured_output_type(self) -> type[PlayerOutputType]:
        """The structured output type for the player.

        This is used to determine what the agent can output.
        """
        return self.protocol.output_type
