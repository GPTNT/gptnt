from typing import Literal, Self, Union, cast

from pydantic import BaseModel
from pydantic.fields import Field, computed_field
from pydantic.functional_validators import model_validator
from pydantic_ai.usage import UsageLimits

from gptnt.players.actions import (
    DoNothingAction,
    DoNothingActionWithThoughts,
    InteractGameAction,
    InteractGameActionWithThoughts,
    PlayerOutputType,
    SendMessageAction,
    SendMessageActionWithThoughts,
    SingleAlphabetLetter,
)

NO_NEW_MESSAGES_SENTINEL = "<no_new_messages>"
"""Sentinel for no new messages."""

type PlayerRole = Literal["defuser", "expert"]
type PlayerType = Literal["ai", "human"]
type CommunicationStyle = Literal["async", "sync"]
type ThinkingFramework = Literal["act", "react", "redact", "dreact"]


class PlayerMetadata(BaseModel, frozen=True):
    """Information about a player."""

    player_type: PlayerType
    """The type of player (AI or human)."""

    player_name: str
    """The name of the player."""

    supports_structured_output: bool
    """Whether the player supports structured output."""

    max_observation_window_length: int = 16
    """The maximum observation window length for the player.

    We default this to 16.
    """

    usage_limits: UsageLimits = Field(default_factory=UsageLimits)
    """The usage limits for the player/model.

    Only really matters if the player is an AI player.
    """


class PlayerSpec(BaseModel, frozen=True):
    """Specification for a player within an experiment."""

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

    @property
    def output_type(self) -> type[PlayerOutputType]:
        """The output type for the player.

        This is used to determine what the agent can output.
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
        return self.is_playing_alone and self.role == "defuser" and self.include_manual

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
    """Dependencies for the AI player."""

    spec: PlayerSpec
    metadata: PlayerMetadata

    @property
    def output_type(self) -> type[PlayerOutputType] | type[str]:
        """The output type for the player.

        This is used to determine what the agent can output.
        """
        return self.structured_output_type if self.metadata.supports_structured_output else str

    @property
    def structured_output_type(self) -> type[PlayerOutputType]:
        """The structured output type for the player.

        This is used to determine what the agent can output.
        """
        return self.spec.output_type
