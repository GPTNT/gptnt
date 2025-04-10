from typing import Annotated, NamedTuple

from pydantic import BaseModel, Field

from gptnt.ktane.state import constants


class BaseModuleState(BaseModel):
    """Base class for all module states."""

    is_solved: bool
    in_focus: bool


class ButtonModuleState(BaseModuleState):
    """State of the Button module."""

    button_color: constants.ButtonColor
    button_word: constants.ButtonWord
    is_held: bool
    strip_colour: constants.ButtonStripColour | None


class KeyPadButtonState(BaseModuleState):
    """State of the Keypad button."""

    symbol: constants.KeypadSymbol
    colour: constants.KeyPadButtonColour | None


class KeypadModuleState(BaseModuleState):
    """State of the Keypad module."""

    top_left: KeyPadButtonState
    top_right: KeyPadButtonState
    bottom_left: KeyPadButtonState
    bottom_right: KeyPadButtonState


class SimonSaysModuleState(BaseModuleState):
    """State of the Simon Says module."""

    beep_sequence: Annotated[list[constants.SimonSaysColor], Field(min_length=1, max_length=5)]
    input_sequence: Annotated[list[constants.SimonSaysColor], Field(min_length=0, max_length=4)]


class BaseWire[WireColourT](BaseModuleState):
    """Base class for wires."""

    is_cut: bool
    colour: WireColourT


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


class ComplicatedWiresModuleState(BaseModuleState):
    """State of the Complicated Wires module."""

    wires: Annotated[list[ComplicatedWire], Field(max_length=6, min_length=1)]


class WireSequenceModuleState(BaseModuleState):
    """State of the Wire Sequence module."""

    panel: Annotated[int, Field(max_length=4, min_length=1)]
    wires: Annotated[list[WireSequenceWire], Field(max_length=3, min_length=1)]


class WireSetModuleState(BaseModuleState):
    """State of the Wire Set module."""

    wires: Annotated[list[WireSetWire], Field(max_length=6, min_length=1)]


class MazeCoordinate(NamedTuple):
    """Coordinate for the maze."""

    row: int
    column: int


class MazeModuleState(BaseModuleState):
    """State of the Maze module.

    Note: Coordinates start with (0,0) at the top-left corner, and (num_rows-1, num_columns-1) at the bottom-right corner.
    (The `-1` is because the coordinates are 0-indexed.)
    """

    num_rows: int
    num_columns: int

    triangle_position: MazeCoordinate
    square_position: MazeCoordinate
    circle_positions: Annotated[list[MazeCoordinate], Field(max_length=2, min_length=2)]


class MemoryModuleState(BaseModuleState):
    """State of the Memory module."""

    display_number: Annotated[int, Field(le=4, ge=1)]
    button_numbers: Annotated[
        list[Annotated[int, Field(le=4, ge=1)]], Field(max_length=4, min_length=4)
    ]
    stage: Annotated[int, Field(le=5, ge=1)]


class MorseCodeModuleState(BaseModuleState):
    """State of the Morse Code module."""

    sequence: constants.MorseCodes
    frequency: float


class PasswordModuleState(BaseModuleState):
    """State of the Password module."""

    letters: list[str]


class WhosOnFirstModuleState(BaseModuleState):
    """State of the Who's on First module."""

    display_word: str
    button_words: list[str]
    stage: Annotated[int, Field(le=3, ge=1)]


type StandardModuleStates = (
    WireSetModuleState
    | ButtonModuleState
    | KeypadModuleState
    | SimonSaysModuleState
    | ComplicatedWiresModuleState
    | MazeModuleState
    | MemoryModuleState
    | MorseCodeModuleState
    | PasswordModuleState
    | WhosOnFirstModuleState
    | WireSequenceModuleState
)


class DischargeModuleState(BaseModuleState):
    """State of the Capacitor Discharge module."""

    is_being_needy: bool
    seconds_until_discharge: int


class KnobModuleState(BaseModuleState):
    """State of the Knob module."""

    is_being_needy: bool
    knob_position: constants.KnobPosition
    led_position: dict[Annotated[int, Field(le=11, ge=0)], bool]  # noqa: WPS432


class GasModuleState(BaseModuleState):
    """State of the Venting Gas module."""

    is_being_needy: bool
    message: constants.GasMessages
    timer: int


type NeedyModuleStates = DischargeModuleState | KnobModuleState | GasModuleState
type ModuleStates = StandardModuleStates | NeedyModuleStates
