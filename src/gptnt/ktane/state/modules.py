from typing import Annotated, Any, Literal, NamedTuple, get_args, override

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Discriminator,
    Field,
    NonNegativeFloat,
    alias_generators,
    computed_field,
    field_validator,
)
from pydantic.types import Tag

from gptnt.ktane.state.module_registry import module_registry

type _KnownKtaneModuleId = Literal[
    "Wires",
    "BigButton",
    "Keypad",
    "Simon",
    "Venn",
    "Maze",
    "Memory",
    "Morse",
    "Password",
    "WhosOnFirst",
    "WireSequence",
    "NeedyCapacitor",
    "NeedyKnob",
    "NeedyVentGas",
]
"""All known module identifiers from Ktane that also have a typed module state class."""

type KtaneModuleId = _KnownKtaneModuleId | str
"""Module identifiers in Ktane.

Yes, it is a bit silly to have a union of a literal and str, but it's the only way to get the
typing to work correctly with the discriminated union for the known module states.
"""

KNOWN_KTANE_MODULE_IDS: frozenset[KtaneModuleId] = frozenset(
    get_args(_KnownKtaneModuleId.__value__)
)
"""Module identifiers that have typed state models in GPTNT."""


def _coerce_color(value: str | None) -> str | None:  # noqa: WPS110
    """Coerce the color to lowercase.

    This is used to ensure that the color is always in lowercase, as the KTANE API expects it to
    be.
    """
    if value is None:
        return None
    return value.lower()


class BaseModuleState(BaseModel):
    """Base class for all module states."""

    model_config = ConfigDict(
        alias_generator=alias_generators.to_camel, populate_by_name=True, extra="allow"
    )

    name: KtaneModuleId

    on_front: bool
    index: Annotated[int, Field(ge=0, le=5)]

    @computed_field
    @property
    def module_location(self) -> int:
        """Get the module location.

        The module location is the index of the module in the list of modules.
        """
        index = self.index
        if self.on_front:
            index += 6
        return index


class InteractiveModuleState(BaseModuleState):
    """Base class for interactive module states.

    This also works for community modules that do not have a typed state class so we can still keep
    track of some information from them.
    """

    is_solved: bool
    in_focus: bool

    @computed_field
    @property
    def needs_multiple_images(self) -> bool:
        """Check if the module needs multiple images.

        This is used to determine if the module needs multiple images to be solved.
        """
        return module_registry().needs_multiple_frames(self.name)


class TimerState(BaseModuleState):
    """State of the Timer module."""

    name: KtaneModuleId = "Timer"
    seconds_remaining: Annotated[
        float, NonNegativeFloat, BeforeValidator(lambda seconds: max(seconds, 0))
    ] = 300


class ButtonModuleState(InteractiveModuleState):
    """State of the Button module."""

    name: KtaneModuleId = "BigButton"

    button_color: str
    button_word: str
    is_held: bool
    strip_color: str | None

    @field_validator("strip_color", "button_color", mode="before")
    @classmethod
    def fix_color(cls, value: str | None) -> str | None:  # noqa: WPS110
        """Coerce the color."""
        return _coerce_color(value)


class KeyPadButtonState(BaseModel):
    """State of the Keypad button."""

    symbol: str
    color: str | None

    @field_validator("color", mode="before")
    @classmethod
    def fix_color(cls, value: str | None) -> str | None:  # noqa: WPS110
        """Coerce the strip color."""
        return _coerce_color(value)


class KeypadModuleState(InteractiveModuleState):
    """State of the Keypad module."""

    name: KtaneModuleId = "Keypad"
    top_left: KeyPadButtonState
    top_right: KeyPadButtonState
    bottom_left: KeyPadButtonState
    bottom_right: KeyPadButtonState


class SimonSaysModuleState(InteractiveModuleState):
    """State of the Simon Says module."""

    name: KtaneModuleId = "Simon"
    beep_sequence: Annotated[
        list[Literal["red", "blue", "green", "yellow"]], Field(min_length=1, max_length=6)
    ]
    solve_progress: Annotated[int, Field(le=5, ge=0)]

    @field_validator("beep_sequence", mode="before")
    @classmethod
    def fix_color(cls, value: list[str] | None) -> list[str]:  # noqa: WPS110
        """Coerce the color to lowercase."""
        if value is not None:
            return [color.lower() for color in value]
        return []


class BaseWire[WireColorT](BaseModel):
    """Base class for wires."""

    model_config = ConfigDict(alias_generator=alias_generators.to_camel, populate_by_name=True)

    is_cut: bool
    color: Annotated[WireColorT, BeforeValidator(lambda word: word.lower())]


class WireSetWire(BaseWire[str]):
    """Wire for the 'Wire Set' module."""

    position: Annotated[int, Field(le=5, ge=0)]


class ComplicatedWire(BaseWire[str]):
    """Wire for the 'Complicated Wires' module."""

    position: Annotated[int, Field(le=5, ge=0)]
    is_led_on: bool
    has_star: bool


class WireSequenceWire(BaseWire[str]):
    """Wire for the 'Wire Sequence' module."""

    start_position_number: int
    end_position_letter: Annotated[str, Field(max_length=1, min_length=1)]


class ComplicatedWiresModuleState(InteractiveModuleState):
    """State of the Complicated Wires module.

    Default wire colours are: white, red, blue, red-white, blue-white, red-blue
    """

    name: KtaneModuleId = "Venn"
    wires: Annotated[list[ComplicatedWire], Field(max_length=6, min_length=1)]

    @field_validator("wires", mode="before")
    @classmethod
    def remove_nones_from_list(
        cls, wires: list[ComplicatedWire | None] | None
    ) -> list[ComplicatedWire]:
        """Remove Nones from the list of wires.

        This is used to ensure that the list of wires is always in the correct format.
        """
        if wires is not None:
            return [wire for wire in wires if wire is not None]
        return []


class WireSequenceModuleState(InteractiveModuleState):
    """State of the Wire Sequence module.

    Default wire colours are: red, blue, black
    """

    name: KtaneModuleId = "WireSequence"
    panel: Annotated[int, Field(le=5, ge=1)]
    wires: Annotated[list[WireSequenceWire], Field(max_length=12, min_length=1)]
    is_emerged: bool = True

    @field_validator("wires", mode="before")
    @classmethod
    def remove_nones_from_list(
        cls, wires: list[WireSequenceWire | None] | None
    ) -> list[WireSequenceWire]:
        """Remove Nones from the list of wires.

        This is used to ensure that the list of wires is always in the correct format.
        """
        if wires is not None:
            return [wire for wire in wires if wire is not None]
        return []

    @property
    def panel_wires(self) -> list[WireSequenceWire]:
        """Get the wires for the current panel."""
        return [
            wire for wire in self.wires if (wire.start_position_number // 3) == (self.panel - 1)
        ]


class WireSetModuleState(InteractiveModuleState):
    """State of the Wire Set module.

    Default wire colours are: red, blue, black, yellow, white
    """

    name: KtaneModuleId = "Wires"
    wires: Annotated[list[WireSetWire], Field(max_length=6, min_length=1)]

    @field_validator("wires", mode="before")
    @classmethod
    def remove_nones_from_list(cls, wires: list[WireSetWire | None] | None) -> list[WireSetWire]:
        """Remove Nones from the list of wires.

        This is used to ensure that the list of wires is always in the correct format.
        """
        if wires is not None:
            return [wire for wire in wires if wire is not None]
        return []


class MazeCoordinate(NamedTuple):
    """Coordinate for the maze."""

    row: int
    column: int

    @override
    def __str__(self) -> str:
        """Get the string representation of the coordinate.

        This is used to ensure that the coordinate is always in the correct format.
        """
        return f"{self.row},{self.column}"


class MazeModuleState(InteractiveModuleState):
    """State of the Maze module.

    Note: Coordinates start with (0,0) at the top-left corner, and (num_rows-1, num_columns-1)
    at the bottom-right corner.
    (The `-1` is because the coordinates are 0-indexed.)
    """

    name: KtaneModuleId = "Maze"
    num_rows: int
    num_columns: int
    triangle_position: MazeCoordinate
    square_position: MazeCoordinate
    circle_positions: Annotated[list[MazeCoordinate], Field(max_length=2, min_length=2)]


class MemoryModuleState(InteractiveModuleState):
    """State of the Memory module."""

    name: KtaneModuleId = "Memory"
    display_number: Annotated[int, Field(le=4, ge=1)] | None
    button_numbers: (
        Annotated[list[Annotated[int, Field(le=4, ge=1)]], Field(max_length=4, min_length=4)]
        | None
    )
    stage: Annotated[int, Field(le=5, ge=0)]
    is_emerged: bool = True


class MorseCodeModuleState(InteractiveModuleState):
    """State of the Morse Code module."""

    name: KtaneModuleId = "Morse"
    sequence: str
    current_frequency: float
    correct_frequency: float


class PasswordModuleState(InteractiveModuleState):
    """State of the Password module."""

    name: KtaneModuleId = "Password"
    current_word: str
    goal_word: str


class WhosOnFirstModuleState(InteractiveModuleState):
    """State of the Who's on First module."""

    name: KtaneModuleId = "WhosOnFirst"
    display_word: str | None
    button_words: list[str] | None
    stage: Annotated[int, Field(le=4, ge=1)]
    is_emerged: bool = True


class DischargeModuleState(InteractiveModuleState):
    """State of the Capacitor Discharge module."""

    name: KtaneModuleId = "NeedyCapacitor"
    is_being_needy: bool
    seconds_until_discharge: int


class KnobModuleState(InteractiveModuleState):
    """State of the Knob module."""

    name: KtaneModuleId = "NeedyKnob"
    is_being_needy: bool
    knob_position: str
    led_position: dict[Annotated[int, Field(le=11, ge=0)], bool]  # noqa: WPS432


class GasModuleState(InteractiveModuleState):
    """State of the Venting Gas module."""

    name: KtaneModuleId = "NeedyVentGas"
    is_being_needy: bool
    message: str
    timer: int


_GENERIC_MODULE_TAG = "Modded"
"""Discriminator tag for a module with no typed state class."""


def _get_discriminator_value(module_state: BaseModuleState | dict[str, Any]) -> str:
    """Return a module's identifier when a typed state member matches it, else the generic tag."""
    name = module_state.name if isinstance(module_state, BaseModel) else module_state["name"]
    tag = str(name)
    return tag if tag in KNOWN_KTANE_MODULE_IDS else _GENERIC_MODULE_TAG


# Note: the Tags need to match KtaneModuleId
type ModuleStates = Annotated[
    (
        Annotated[WireSetModuleState, Tag("Wires")]
        | Annotated[ButtonModuleState, Tag("BigButton")]
        | Annotated[KeypadModuleState, Tag("Keypad")]
        | Annotated[SimonSaysModuleState, Tag("Simon")]
        | Annotated[ComplicatedWiresModuleState, Tag("Venn")]
        | Annotated[MazeModuleState, Tag("Maze")]
        | Annotated[MemoryModuleState, Tag("Memory")]
        | Annotated[MorseCodeModuleState, Tag("Morse")]
        | Annotated[PasswordModuleState, Tag("Password")]
        | Annotated[WhosOnFirstModuleState, Tag("WhosOnFirst")]
        | Annotated[WireSequenceModuleState, Tag("WireSequence")]
        | Annotated[DischargeModuleState, Tag("NeedyCapacitor")]
        | Annotated[KnobModuleState, Tag("NeedyKnob")]
        | Annotated[GasModuleState, Tag("NeedyVentGas")]
        | Annotated[InteractiveModuleState, Tag(_GENERIC_MODULE_TAG)]
    ),
    Discriminator(_get_discriminator_value),
]
