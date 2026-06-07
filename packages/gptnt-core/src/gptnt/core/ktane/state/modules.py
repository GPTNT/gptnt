import types
from enum import Enum
from typing import Annotated, Any, NamedTuple, override

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

from gptnt.core.ktane.state import constants


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


NEEDS_MULTIPLE_IMAGES = types.MappingProxyType(
    {
        KtaneComponent.wires: False,
        KtaneComponent.big_button: False,
        KtaneComponent.keypad: False,
        # because of the blinking lights
        KtaneComponent.simon: True,
        KtaneComponent.whos_on_first: False,
        KtaneComponent.memory: False,
        # because of the blinking lights
        KtaneComponent.morse_code: True,
        KtaneComponent.venn: False,
        KtaneComponent.wire_sequence: False,
        KtaneComponent.maze: False,
        KtaneComponent.password: False,
    }
)
"""Whether a module requires multiple images/frames to be solved."""


class BaseModuleState(BaseModel):
    """Base class for all module states."""

    model_config = ConfigDict(
        alias_generator=alias_generators.to_camel, populate_by_name=True, extra="ignore"
    )

    name: KtaneComponent

    on_front: bool
    index: Annotated[int, Field(ge=0, le=5)]

    @field_validator("name", mode="before")
    @classmethod
    def coerce_name(cls, value: str) -> KtaneComponent:  # noqa: WPS110
        """Coerce the name to a KtaneComponent."""
        return KtaneComponent(value)

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

    @computed_field
    @property
    def needs_multiple_images(self) -> bool:
        """Check if the module needs multiple images.

        This is used to determine if the module needs multiple images to be solved.
        """
        return NEEDS_MULTIPLE_IMAGES[self.name]


class TimerState(BaseModuleState):
    """State of the Timer module."""

    seconds_remaining: Annotated[
        float, NonNegativeFloat, BeforeValidator(lambda seconds: max(seconds, 0))
    ] = 300


class ButtonModuleState(InteractiveModuleState):
    """State of the Button module."""

    name: KtaneComponent = KtaneComponent.big_button

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

    name: KtaneComponent = KtaneComponent.keypad
    top_left: KeyPadButtonState
    top_right: KeyPadButtonState
    bottom_left: KeyPadButtonState
    bottom_right: KeyPadButtonState


class SimonSaysModuleState(InteractiveModuleState):
    """State of the Simon Says module."""

    name: KtaneComponent = KtaneComponent.simon
    beep_sequence: Annotated[list[constants.SimonSaysColor], Field(min_length=1, max_length=6)]
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

    name: KtaneComponent = KtaneComponent.venn
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
    """State of the Wire Sequence module."""

    name: KtaneComponent = KtaneComponent.wire_sequence
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
    """State of the Wire Set module."""

    name: KtaneComponent = KtaneComponent.wires
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

    Note: Coordinates start with (0,0) at the top-left corner, and (num_rows-1, num_columns-1) at the bottom-right corner.
    (The `-1` is because the coordinates are 0-indexed.)
    """

    name: KtaneComponent = KtaneComponent.maze
    num_rows: int
    num_columns: int
    triangle_position: MazeCoordinate
    square_position: MazeCoordinate
    circle_positions: Annotated[list[MazeCoordinate], Field(max_length=2, min_length=2)]


class MemoryModuleState(InteractiveModuleState):
    """State of the Memory module."""

    name: KtaneComponent = KtaneComponent.memory
    display_number: Annotated[int, Field(le=4, ge=1)] | None
    button_numbers: (
        Annotated[list[Annotated[int, Field(le=4, ge=1)]], Field(max_length=4, min_length=4)]
        | None
    )
    stage: Annotated[int, Field(le=5, ge=0)]
    is_emerged: bool = True


class MorseCodeModuleState(InteractiveModuleState):
    """State of the Morse Code module."""

    name: KtaneComponent = KtaneComponent.morse_code
    sequence: str
    current_frequency: float
    correct_frequency: float


class PasswordModuleState(InteractiveModuleState):
    """State of the Password module."""

    name: KtaneComponent = KtaneComponent.password
    current_word: str
    goal_word: str


class WhosOnFirstModuleState(InteractiveModuleState):
    """State of the Who's on First module."""

    name: KtaneComponent = KtaneComponent.whos_on_first
    display_word: str | None
    button_words: list[str] | None
    stage: Annotated[int, Field(le=4, ge=1)]
    is_emerged: bool = True


class DischargeModuleState(InteractiveModuleState):
    """State of the Capacitor Discharge module."""

    name: KtaneComponent = KtaneComponent.needy_capacitor
    is_being_needy: bool
    seconds_until_discharge: int


class KnobModuleState(InteractiveModuleState):
    """State of the Knob module."""

    name: KtaneComponent = KtaneComponent.needy_knob
    is_being_needy: bool
    knob_position: constants.KnobPosition
    led_position: dict[Annotated[int, Field(le=11, ge=0)], bool]  # noqa: WPS432


class GasModuleState(InteractiveModuleState):
    """State of the Venting Gas module."""

    name: KtaneComponent = KtaneComponent.needy_vent_gas
    is_being_needy: bool
    message: constants.GasMessages
    timer: int


def _get_discriminator_value(module_state: BaseModuleState | dict[str, Any]) -> str:
    """Get the discriminator value for a module state."""
    if isinstance(module_state, BaseModel):
        return module_state.name.value
    return module_state["name"]


# Note: the Tags need to match the KtaneComponent values
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
    ),
    Discriminator(_get_discriminator_value),
]
