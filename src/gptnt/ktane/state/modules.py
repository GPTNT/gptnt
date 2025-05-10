from enum import Enum
from typing import Annotated, NamedTuple

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    NonNegativeFloat,
    alias_generators,
    computed_field,
    field_validator,
)
from pydantic.types import Tag

from gptnt.ktane.state import constants


class KtaneComponent(Enum):
    """Enum representing valid KTANE components."""

    empty = "Empty"
    timer = "Timer"
    wires = "Wires"
    big_button = "BigButton"
    keypad = "Keypad"
    simon = "Simon"
    whos_on_first = "WhosOnFirst"
    memory = "Memory"
    morse_code = "Morse"
    venn = "Venn"
    wire_sequence = "WireSequence"
    maze = "Maze"
    password = "Password"  # noqa: S105
    needy_vent_gas = "NeedyVentGas"
    needy_capacitor = "NeedyCapacitor"
    needy_knob = "NeedyKnob"


def coerce_color(value: str | None) -> str | None:  # noqa: WPS110
    """Coerce the color to lowercase.

    This is used to ensure that the color is always in lowercase, as the KTANE API expects it to
    be.
    """
    if value is None:
        return None
    return value.lower()


class BaseModuleState(BaseModel):
    """Base class for all module states."""

    model_config = ConfigDict(alias_generator=alias_generators.to_camel, populate_by_name=True)

    name: KtaneComponent

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
    """Base class for interactive module states."""

    is_solved: bool
    in_focus: bool


class TimerState(BaseModuleState):
    """State of the Timer module."""

    seconds_remaining: Annotated[
        float, NonNegativeFloat, BeforeValidator(lambda seconds: max(seconds, 0))
    ] = 300


class ButtonModuleState(InteractiveModuleState):
    """State of the Button module."""

    button_color: constants.ButtonColor
    button_word: constants.ButtonWord
    is_held: bool
    strip_color: constants.ButtonStripColor | None

    @field_validator("strip_color", "button_color", mode="before")
    @classmethod
    def fix_color(cls, value: str | None) -> str | None:  # noqa: WPS110
        """Coerce the color."""
        return coerce_color(value)


class KeyPadButtonState(BaseModel):
    """State of the Keypad button."""

    symbol: constants.KeypadSymbol
    color: constants.KeyPadButtonColor | None

    @field_validator("color", mode="before")
    @classmethod
    def fix_color(cls, value: str | None) -> str | None:  # noqa: WPS110
        """Coerce the strip color."""
        return coerce_color(value)


class KeypadModuleState(InteractiveModuleState):
    """State of the Keypad module."""

    top_left: KeyPadButtonState
    top_right: KeyPadButtonState
    bottom_left: KeyPadButtonState
    bottom_right: KeyPadButtonState


class SimonSaysModuleState(InteractiveModuleState):
    """State of the Simon Says module."""

    beep_sequence: Annotated[list[constants.SimonSaysColor], Field(min_length=1, max_length=6)]
    solve_progress: Annotated[int, Field(le=5, ge=0)]

    @field_validator("beep_sequence", mode="before")
    @classmethod
    def fix_color(cls, value: list[str]) -> list[str]:  # noqa: WPS110
        """Coerce the color to lowercase."""
        return [color.lower() for color in value]


class BaseWire[WireColorT](BaseModel):
    """Base class for wires."""

    model_config = ConfigDict(alias_generator=alias_generators.to_camel, populate_by_name=True)

    is_cut: bool
    color: Annotated[WireColorT, BeforeValidator(lambda word: word.lower())]


class WireSetWire(BaseWire[constants.WireSetColor]):
    """Wire for the 'Wire Set' module."""

    position: Annotated[int, Field(le=5, ge=0)]


class ComplicatedWire(BaseWire[constants.ComplicatedWireColor]):
    """Wire for the 'Complicated Wires' module."""

    position: Annotated[int, Field(le=5, ge=0)]
    is_led_on: bool
    has_star: bool


class WireSequenceWire(BaseWire[constants.WireSequenceColor]):
    """Wire for the 'Wire Sequence' module."""

    start_position_number: int
    end_position_letter: Annotated[str, Field(max_length=1, min_length=1)]


class ComplicatedWiresModuleState(InteractiveModuleState):
    """State of the Complicated Wires module."""

    wires: Annotated[list[ComplicatedWire], Field(max_length=6, min_length=1)]

    @field_validator("wires", mode="before")
    @classmethod
    def remove_nones_from_list(cls, wires: list[ComplicatedWire | None]) -> list[ComplicatedWire]:
        """Remove Nones from the list of wires.

        This is used to ensure that the list of wires is always in the correct format.
        """
        return [wire for wire in wires if wire is not None]


class WireSequenceModuleState(InteractiveModuleState):
    """State of the Wire Sequence module."""

    panel: Annotated[int, Field(le=4, ge=1)]
    wires: Annotated[list[WireSequenceWire], Field(max_length=12, min_length=1)]

    @field_validator("wires", mode="before")
    @classmethod
    def remove_nones_from_list(
        cls, wires: list[WireSequenceWire | None]
    ) -> list[WireSequenceWire]:
        """Remove Nones from the list of wires.

        This is used to ensure that the list of wires is always in the correct format.
        """
        return [wire for wire in wires if wire is not None]


class WireSetModuleState(InteractiveModuleState):
    """State of the Wire Set module."""

    wires: Annotated[list[WireSetWire], Field(max_length=6, min_length=1)]

    @field_validator("wires", mode="before")
    @classmethod
    def remove_nones_from_list(cls, wires: list[WireSetWire | None]) -> list[WireSetWire]:
        """Remove Nones from the list of wires.

        This is used to ensure that the list of wires is always in the correct format.
        """
        return [wire for wire in wires if wire is not None]


class MazeCoordinate(NamedTuple):
    """Coordinate for the maze."""

    row: int
    column: int


class MazeModuleState(InteractiveModuleState):
    """State of the Maze module.

    Note: Coordinates start with (0,0) at the top-left corner, and (num_rows-1, num_columns-1) at the bottom-right corner.
    (The `-1` is because the coordinates are 0-indexed.)
    """

    num_rows: int
    num_columns: int
    triangle_position: MazeCoordinate
    square_position: MazeCoordinate
    circle_positions: Annotated[list[MazeCoordinate], Field(max_length=2, min_length=2)]


class MemoryModuleState(InteractiveModuleState):
    """State of the Memory module."""

    display_number: Annotated[int, Field(le=4, ge=1)]
    button_numbers: Annotated[
        list[Annotated[int, Field(le=4, ge=1)]], Field(max_length=4, min_length=4)
    ]
    stage: Annotated[int, Field(le=5, ge=0)]


class MorseCodeModuleState(InteractiveModuleState):
    """State of the Morse Code module."""

    sequence: str
    current_frequency: float
    correct_frequency: float


class PasswordModuleState(InteractiveModuleState):
    """State of the Password module."""

    current_word: str
    goal_word: str


class WhosOnFirstModuleState(InteractiveModuleState):
    """State of the Who's on First module."""

    display_word: str
    button_words: list[str]
    stage: Annotated[int, Field(le=4, ge=1)]


class DischargeModuleState(InteractiveModuleState):
    """State of the Capacitor Discharge module."""

    is_being_needy: bool
    seconds_until_discharge: int


class KnobModuleState(InteractiveModuleState):
    """State of the Knob module."""

    is_being_needy: bool
    knob_position: constants.KnobPosition
    led_position: dict[Annotated[int, Field(le=11, ge=0)], bool]  # noqa: WPS432


class GasModuleState(InteractiveModuleState):
    """State of the Venting Gas module."""

    is_being_needy: bool
    message: constants.GasMessages
    timer: int


type StandardModuleStates = (
    Annotated[WireSetModuleState, Tag("WireSet")]
    | Annotated[ButtonModuleState, Tag("Button")]
    | Annotated[KeypadModuleState, Tag("Keypad")]
    | Annotated[SimonSaysModuleState, Tag("Simon")]
    | Annotated[ComplicatedWiresModuleState, Tag("ComplicatedWires")]
    | Annotated[MazeModuleState, Tag("Maze")]
    | Annotated[MemoryModuleState, Tag("Memory")]
    | Annotated[MorseCodeModuleState, Tag("Morse")]
    | Annotated[PasswordModuleState, Tag("Password")]
    | Annotated[WhosOnFirstModuleState, Tag("WhosOnFirst")]
    | Annotated[WireSequenceModuleState, Tag("WireSequence")]
)

type NeedyModuleStates = (
    Annotated[DischargeModuleState, Tag("NeedyCapacitor")]
    | Annotated[KnobModuleState, Tag("NeedyKnob")]
    | Annotated[GasModuleState, Tag("NeedyVentGas")]
)
type ModuleStates = (
    Annotated[StandardModuleStates, Tag("Standard")] | Annotated[NeedyModuleStates, Tag("Needy")]
)
