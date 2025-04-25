from enum import Enum
from typing import Annotated, NamedTuple, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeFloat,
    alias_generators,
    computed_field,
)

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

    seconds_remaining: NonNegativeFloat = 300


class ButtonModuleState(InteractiveModuleState):
    """State of the Button module."""

    button_color: constants.ButtonColor
    button_word: constants.ButtonWord
    is_held: bool
    strip_color: constants.ButtonStripColor | None


class KeyPadButtonState(BaseModel):
    """State of the Keypad button."""

    symbol: constants.KeypadSymbol
    color: constants.KeyPadButtonColor | None


class KeypadModuleState(InteractiveModuleState):
    """State of the Keypad module."""

    top_left: KeyPadButtonState
    top_right: KeyPadButtonState
    bottom_left: KeyPadButtonState
    bottom_right: KeyPadButtonState


class SimonSaysModuleState(InteractiveModuleState):
    """State of the Simon Says module."""

    beep_sequence: Annotated[list[constants.SimonSaysColor], Field(min_length=4, max_length=6)]
    solve_progress: Annotated[int, Field(le=5, ge=0)]


class BaseWire[WireColorT](BaseModel):
    """Base class for wires."""

    model_config = ConfigDict(alias_generator=alias_generators.to_camel, populate_by_name=True)

    is_cut: bool
    color: WireColorT


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


class WireSequenceModuleState(InteractiveModuleState):
    """State of the Wire Sequence module."""

    panel: Annotated[int, Field(le=4, ge=1)]
    wires: Annotated[list[WireSequenceWire], Field(max_length=3, min_length=1)]


class WireSetModuleState(InteractiveModuleState):
    """State of the Wire Set module."""

    wires: Annotated[list[WireSetWire], Field(max_length=6, min_length=1)]


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
    stage: Annotated[int, Field(le=5, ge=1)]


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
    stage: Annotated[int, Field(le=3, ge=1)]


type StandardModuleStates = Union[  # noqa: UP007
    WireSetModuleState,
    ButtonModuleState,
    KeypadModuleState,
    SimonSaysModuleState,
    ComplicatedWiresModuleState,
    MazeModuleState,
    MemoryModuleState,
    MorseCodeModuleState,
    PasswordModuleState,
    WhosOnFirstModuleState,
    WireSequenceModuleState,
]


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


type NeedyModuleStates = DischargeModuleState | KnobModuleState | GasModuleState
type ModuleStates = StandardModuleStates | NeedyModuleStates
