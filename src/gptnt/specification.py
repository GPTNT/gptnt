from typing import Literal, Self, override

from pydantic import BaseModel, ConfigDict, Field
from pydantic.fields import computed_field
from pydantic.functional_validators import model_validator
from pydantic_ai.output import StructuredOutputMode
from pydantic_ai.usage import UsageLimits

from gptnt.common.image_ops import ImageDimensions
from gptnt.ktane.game_settings import KtaneSettings
from gptnt.players.locations import (
    CoordinateMode,
    InteractionLocationMethod,
    PixelLocation,
    ScaledLocation,
    SingleAlphabetLetter,
)

type PlayerType = Literal["ai", "human"]
type PlayerRole = Literal["defuser", "expert"]
type CommunicationStyle = Literal["async", "sync"]
type ThinkingMethod = Literal["inner-monologue", "thinking-out-loud"]
"""Thinking method used by players.

- "inner-monologue": Model reasoning is kept separate from the user-visible message (parsed as
                    `ThinkingPart` from the model output; the prompt format uses a dedicated
                    `<think>` section).
- "thinking-out-loud": Reasoning is part of the normal message flow (ReAct-style).
"""


class PlayerCapabilities(BaseModel):
    """The capabilities of a player, that is set once on instantiation.

    This tells the EM what the player is and what they can do for the matchmaking.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    player_name: str
    """The name of the player."""

    player_type: PlayerType
    """The type of player (AI or human)."""

    thinking_method: ThinkingMethod = "inner-monologue"
    """The thinking method of the player."""

    structured_output_mode: StructuredOutputMode | None = "prompted"
    """Which structured output mode to use, as per pydantic-ai."""

    include_schema_in_instructions: bool = True
    """Should we manually include the output schema in the instructions."""

    max_observations_per_request: int = 16
    """The maximum number of observations per request for the player.

    We default this to 16.
    """

    usage_limits: UsageLimits = Field(default_factory=UsageLimits)

    image_dimensions: ImageDimensions = Field(default=KtaneSettings().image_dimensions)
    """Width and height for the player's input images.

    Default to KTANE settings.
    """

    interaction_location_method: InteractionLocationMethod = "set-of-marks"
    """Whether interaction locations are predicted as set-of-marks or coordinates."""

    coordinate_mode: CoordinateMode = "absolute"
    """The flavour of coordinates that the model supports.

    Normalised coordinates are on a scale from 0 to 1000, while absolute coordinates are in pixel
    values based on the image dimensions. You can change the ranges of normalised coordinates in
    the ScaledLocation class var.
    """

    preserve_last_frame_for_n_turns: int = 0
    """Number of previous turns from which to keep the last frame in the observation window."""

    enable_nobf_generation: bool = True
    """Whether to generate Naughty Output Behaviour Feedback for each action."""

    @model_validator(mode="after")
    def validate_no_duplicate_schema_inclusion(self) -> Self:
        """Ensure the schema only appears at maximum once."""
        if self.structured_output_mode == "prompted" and not self.include_schema_in_instructions:
            raise ValueError(
                "If structured outputs are used with 'prompted' mode, the schema is always "
                "included in the instructions, so 'include_schema_in_instructions' cannot be False."
            )
        return self

    @model_validator(mode="after")
    def validate_thinking_mode_output_compatibility(self) -> Self:
        """If the thinking mode is out-loud, ensure that structured outputs are not used."""
        if self.thinking_method == "thinking-out-loud" and self.structured_output_mode is not None:
            raise ValueError(
                "If the thinking mode is 'thinking-out-loud', structured outputs cannot be used."
            )
        return self

    @property
    def interact_location_type(
        self,
    ) -> type[SingleAlphabetLetter] | type[PixelLocation] | type[ScaledLocation]:
        """The type used for interaction locations.

        This is based on the interaction location method so that we can dynamically create the
        output type for the protocol without needing to have a whole different if-statement.
        """
        match self.coordinate_mode:
            case "absolute":
                coordinate_flavour = PixelLocation
            case "normalised":
                coordinate_flavour = ScaledLocation

        match self.interaction_location_method:
            case "set-of-marks":
                return SingleAlphabetLetter  # pyright: ignore[reportReturnType]
            case "coordinates":
                return coordinate_flavour

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

    receive_feedback_after_action: bool = False
    """Whether or not a player should receive feedback after each action."""

    allow_magic_actions: bool = False
    """Whether the player is allowed to perform magic actions."""

    allow_lottery_actions: bool = False
    """Whether the player is allowed to perform lottery actions."""

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


class PlayerSpec(BaseModel):
    """One player in a roster: a model config, an optional provider override, and a count."""

    model_config = ConfigDict(extra="forbid")

    model: str
    """A `configs/model/<model>.yaml` config name."""

    provider: str | None = None
    """A `configs/model/provider/<provider>.yaml` config name, or `None` to use the default."""

    count: int = Field(default=1, ge=1)
    """How many copies of this player to spawn."""
