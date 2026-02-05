import json
from typing import Annotated, ClassVar, Generic, Literal, TypeVar

from annotated_types import MaxLen, Predicate
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, NonNegativeInt, field_validator
from pydantic_ai import BaseToolCallPart, BaseToolReturnPart, ModelMessage, ModelResponse, RunUsage

from gptnt.ktane.actions import GameActionType, KtaneBaseAction, RelativeCoordinate
from gptnt.players.exceptions import AIResponseErrorType

NO_NEW_MESSAGES_SENTINEL = "\n"
"""Sentinel for no new messages."""


class ModelOutputDumpsMixin(BaseModel):
    """Mixin for dumping actions to conform to the JSONSchema from NativeOutput."""

    def text_part_dump(self) -> str:
        """Dump the model output as a string."""
        return json.dumps(
            {
                "result": {
                    "kind": self.model_config.get("title", self.__class__.__name__),
                    "data": self.model_dump(
                        mode="json", exclude_defaults=True, exclude_unset=True
                    ),
                }
            }
        )


class DoNothingAction(ModelOutputDumpsMixin):
    """Create a 'do nothing' action."""

    model_config = ConfigDict(title="do_nothing")


class SendMessageAction(ModelOutputDumpsMixin):
    """Create a 'send message' action."""

    model_config = ConfigDict(title="send_message")

    message: str


class AbsoluteCoordinate(BaseModel):
    """Absolute coordinate to interact with in the game."""

    x: NonNegativeInt  # noqa: WPS111
    """Absolute x-coordinate from the left."""

    y: NonNegativeInt  # noqa: WPS111
    """Absolute y-coordinate from the top."""


class NormalisedCoordinate(BaseModel):
    """Normalised coordinate to interact with in the game, between 0 and 1000."""

    lower_bound: ClassVar[int] = 0
    upper_bound: ClassVar[int] = 1000

    x: NonNegativeInt  # noqa: WPS111
    """Normalised x-coordinate from the left."""

    y: NonNegativeInt  # noqa: WPS111
    """Normalised y-coordinate from the top."""


type SingleAlphabetLetter = Annotated[
    str, MaxLen(1), Predicate(str.isalpha), AfterValidator(lambda letter: letter.upper())
]


type SetOfMarksLocation = NonNegativeInt | SingleAlphabetLetter
"""Set of marks location to interact with; must be an int >= 0, or a single letter A-Z."""

type InteractableLocation = (
    RelativeCoordinate | SetOfMarksLocation | AbsoluteCoordinate | NormalisedCoordinate
)
"""Location-methods to interact with in the game."""

LocationDataT_co = TypeVar("LocationDataT_co", bound=InteractableLocation, covariant=True)


class InteractGameAction(
    KtaneBaseAction[GameActionType, LocationDataT_co],
    ModelOutputDumpsMixin,
    Generic[LocationDataT_co],  # noqa: UP046
):
    """Interaction action for the player to take in the game."""

    model_config = ConfigDict(title="interact_game")


class MagicGameAction(
    KtaneBaseAction[Literal["magic"], InteractableLocation], ModelOutputDumpsMixin
):
    """Magic action for the player to take in the game."""

    model_config = ConfigDict(title="perform_magic")


type GameInteractionActionType = MagicGameAction | InteractGameAction[InteractableLocation]
"""Action types representing only game interaction actions."""


type PlayerOutputType = (
    DoNothingAction
    | SendMessageAction
    | InteractGameAction[InteractableLocation]
    | MagicGameAction
)
"""Any possible output from a player."""


ModelOutputT_co = TypeVar("ModelOutputT_co", covariant=True)


class AgentCallResult(BaseModel, Generic[ModelOutputT_co]):  # noqa: UP046
    """Result of an agent call."""

    output: ModelOutputT_co
    thoughts: str | None

    usage: RunUsage
    new_messages: list[ModelMessage]

    ai_response_error: list[AIResponseErrorType] = Field(default_factory=list)
    raw_output: str | None = None

    @field_validator("new_messages")
    @classmethod
    def check_no_tools_in_messages(cls, messages: list[ModelMessage]) -> list[ModelMessage]:
        """Ensure there are no tool parts in the new messages.

        We do this just to make life easier right now. But that also means we are double-ing down
        on the whole "no using function tools to play the game" aspect of the benchmark.

        Also Pydantic says to use ValueError and not TypeError, hence the noqa.
        """
        for message in messages:
            for part in message.parts:
                if isinstance(part, (BaseToolReturnPart, BaseToolCallPart)):
                    raise ValueError("Tool messages are not allowed in new_messages.")  # noqa: TRY004
        return messages

    @field_validator("new_messages")
    @classmethod
    def check_final_message_is_model_response(
        cls, messages: list[ModelMessage]
    ) -> list[ModelMessage]:
        """Ensure the final message is a ModelResponse."""
        if messages:
            final_message = messages[-1]
            if not isinstance(final_message, ModelResponse):
                raise ValueError("The final message in new_messages must a ModelResponse.")
        return messages
