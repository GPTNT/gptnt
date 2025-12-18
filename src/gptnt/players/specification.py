from typing import Literal, Self, Union, cast, override

from pydantic import BaseModel, ConfigDict, Field
from pydantic.fields import computed_field
from pydantic.functional_validators import model_validator
from pydantic_ai import NativeOutput, PromptedOutput
from pydantic_ai.output import OutputSpec, StructuredOutputMode
from pydantic_ai.usage import UsageLimits

from gptnt.common.image_ops import ImageDimensions
from gptnt.ktane.game_settings import KtaneSettings
from gptnt.players.actions import (
    AbsoluteCoordinate,
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
type ThinkingFramework = Literal["act", "react"]
type CommunicationStyle = Literal["async", "sync"]


class PlayerCapabilities(BaseModel):
    """The capabilities of a player, that is set once on instantiation.

    This tells the EM what the player is and what they can do for the matchmaking.
    """

    model_config = ConfigDict(frozen=True)

    player_name: str
    """The name of the player."""

    player_type: PlayerType
    """The type of player (AI or human)."""

    use_structured_outputs: bool
    """Whether the player supports structured output."""

    structured_output_mode: StructuredOutputMode = "native"
    """Which structured output mode to use, as per pydantic-ai."""

    max_observation_window_length: int = 16
    """The maximum observation window length for the player.

    We default this to 16.
    """

    usage_limits: UsageLimits = Field(default_factory=UsageLimits)

    image_dimensions: ImageDimensions = Field(default=KtaneSettings().image_dimensions)
    """Width and height for the player's input images.

    Default to KTANE settings.
    """

    interaction_location_method: Literal["set-of-marks", "coordinates"] = "set-of-marks"
    """Whether interaction locations are predicted as set-of-marks or coordinates."""

    @property
    def interact_location_type(self) -> type[SingleAlphabetLetter] | type[AbsoluteCoordinate]:
        """The type used for interaction locations.

        This is based on the interaction location method so that we can dynamically create the
        output type for the protocol without needing to have a whole different if-statement.
        """
        match self.interaction_location_method:
            case "set-of-marks":
                return SingleAlphabetLetter  # pyright: ignore[reportReturnType]
            case "coordinates":
                return AbsoluteCoordinate

    @override
    def __hash__(self) -> int:
        """Manually provide the hash function."""
        return hash(self.model_dump_json())


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

    receive_feedback_after_action: bool = False
    """Whether or not a player should receive feedback after each action."""

    allow_magic_actions: bool = False
    """Whether the player is allowed to perform magic actions."""

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


class PlayerDeps(BaseModel, frozen=True):
    """Dependencies for the AI player (as in PydanticAI)."""

    capabilities: PlayerCapabilities
    protocol: PlayerProtocol

    @property
    def output_type(self) -> OutputSpec[PlayerOutputType] | type[str]:
        """The output type for the player.

        This is used to determine what the agent can output.

        Since PydanticAI defaults to the "tool" format if you just give it the type, we can do that
        for the "tool" mode. However, importantly, doing it this way makes the schema output like
        the model has a single tool to call with one of three possible ways of using it. An
        alternative would be to provide a list[ToolOutput], but let's keep it simple for now.
        """
        if self.capabilities.use_structured_outputs:
            match self.capabilities.structured_output_mode:
                case "native":
                    return NativeOutput(self.structured_output_type)
                case "tool":
                    return self.structured_output_type
                case "prompted":
                    return PromptedOutput(self.structured_output_type)
        return str

    @property
    def structured_output_type(self) -> type[PlayerOutputType]:
        """The output type for the player.

        This is used to determine what the agent can output.

        Note that at the end, we also patch the name so that it can be used by various tool
        functions because for some reason, this was not working properly.
        """
        output: list[type[PlayerOutputType]] = []

        if self.protocol.allow_thoughts_output:
            output.append(DoNothingActionWithThoughts)
        else:
            output.append(DoNothingAction)

        if not self.protocol.is_playing_alone:
            if self.protocol.allow_thoughts_output:
                output.append(SendMessageActionWithThoughts)
            else:
                output.append(SendMessageAction)

        if self.protocol.role == "defuser":
            if self.protocol.allow_thoughts_output:
                output.append(
                    InteractGameActionWithThoughts[self.capabilities.interact_location_type]
                )
            else:
                output.append(InteractGameAction[self.capabilities.interact_location_type])

        if self.protocol.allow_magic_actions:
            output.append(MagicGameAction)

        clean_output: list[type[PlayerOutputType]] = []
        for output_type in output:
            # Remove the brackets from the output type name
            output_type.__name__ = output_type.__name__.replace("[", "").replace("]", "")
            output_type.__qualname__ = output_type.__qualname__.replace("[", "").replace("]", "")
            clean_output.append(output_type)

        return cast("type[PlayerOutputType]", Union[tuple(clean_output)])  # noqa: UP007
