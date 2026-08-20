from enum import StrEnum
from functools import partial
from typing import Annotated, Any, Literal, Self, Union

import orjson
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    SerializationInfo,
    SerializerFunctionWrapHandler,
    TypeAdapter,
    WrapSerializer,
    alias_generators,
    model_validator,
)

from gptnt.ktane.state.module_registry import module_registry
from gptnt.ktane.state.modules import KtaneModuleId, ModuleStates, TimerState
from gptnt.ktane.state.widget import WidgetStates


class BombOutcome(StrEnum):
    """Classification of a bomb state's outcome.

    Values include terminal outcomes (solved, timeout, strikeout, and detonated) as well as the
    non-terminal `incomplete` state when the game has not ended.
    """

    solved = "solved"
    timeout = "timeout"
    strikeout = "strikeout"

    detonated = "detonated"
    incomplete = "incomplete"


def _serialise_states_to_string(
    input_value: Any,
    handler: SerializerFunctionWrapHandler,  # noqa: WPS110
    info: SerializationInfo,  # noqa: WPS110
    *,
    obj_type: type,
) -> str:
    """Either we serialize it to string or let the handler do its job."""
    if info.context and info.context.get("serialize_as_string", False):
        return orjson.dumps(TypeAdapter(obj_type).dump_python(input_value, mode="json")).decode()
    return handler(input_value)


def _validate_state_from_string(data: str | Any) -> dict[str, Any]:
    """Validate state from string or pass through."""
    if isinstance(data, str):
        return orjson.loads(data)
    return data


class BombState(BaseModel):
    """State of the bomb at the current timestep.

    This is the canonical representation of the bomb state that we receive from the mod. This
    should be able to tell you everything about the current state of the game in a logical/single
    object.
    """

    model_config = ConfigDict(alias_generator=alias_generators.to_camel, populate_by_name=True)

    seed: int
    max_strikes: int = 3
    strikes: (
        Annotated[
            list[KtaneModuleId],
            BeforeValidator(_validate_state_from_string),
            WrapSerializer(
                partial(_serialise_states_to_string, obj_type=list[KtaneModuleId]),
                when_used="json-unless-none",
                return_type=Union[list[str], str],  # noqa: UP007
            ),
        ]
        | None
    )
    is_detonated: bool
    is_solved: bool
    is_light_on: bool
    bomb_side: Literal["top", "bottom", "left", "right", "front", "back"]
    timer_module: TimerState
    widgets: Annotated[
        list[WidgetStates],
        BeforeValidator(_validate_state_from_string),
        WrapSerializer(
            partial(_serialise_states_to_string, obj_type=list[WidgetStates]),
            when_used="json-unless-none",
            return_type=Union[list[dict[str, Any]], str],  # noqa: UP007
        ),
    ]
    modules: Annotated[
        list[ModuleStates],
        BeforeValidator(_validate_state_from_string),
        WrapSerializer(
            partial(_serialise_states_to_string, obj_type=list[ModuleStates]),
            when_used="json-unless-none",
            return_type=Union[list[dict[str, Any]], str],  # noqa: UP007
        ),
    ]

    @property
    def module_names(self) -> list[KtaneModuleId]:
        """Get the names of all modules on the bomb."""
        return [module.name for module in self.modules]

    @property
    def seconds_remaining(self) -> float:
        """Get the remaining time on the bomb."""
        return self.timer_module.seconds_remaining

    @property
    def zoomed_in_component(self) -> KtaneModuleId | None:
        """Get the currently zoomed in component, if we are zoomed in."""
        for module in self.modules:
            if module.in_focus:
                return module.name
        return None

    @property
    def zoomed_in_module(self) -> ModuleStates | None:
        """Get the currently zoomed in module state, if we are zoomed in."""
        for module in self.modules:
            if module.in_focus:
                return module
        return None

    @property
    def view_needs_multiple_frames(self) -> bool:
        """Check if the current view needs multiple frames."""
        if self.zoomed_in_component is not None:
            return module_registry().needs_multiple_frames(self.zoomed_in_component)
        return False

    @property
    def num_modules_solved(self) -> int:
        """Count how many modules are solved."""
        return sum(module.is_solved for module in self.modules)

    @property
    def is_timed_out(self) -> bool:
        """Check if the bomb is timed out."""
        return self.is_detonated and self.timer_module.seconds_remaining <= 0

    @property
    def is_strike_out(self) -> bool:
        """Check if the bomb is strike out."""
        if not self.strikes:
            return False
        return self.is_detonated and len(self.strikes) >= self.max_strikes

    @property
    def outcome(self) -> BombOutcome:
        """Classify the outcome from the bomb state."""
        if self.is_solved:
            return BombOutcome.solved
        if self.is_timed_out:
            return BombOutcome.timeout
        if self.is_strike_out:
            return BombOutcome.strikeout
        if self.is_detonated:
            return BombOutcome.detonated
        return BombOutcome.incomplete

    @property
    def strike_count(self) -> int:
        """Get the current number of strikes."""
        if not self.strikes:
            return 0
        return len(self.strikes)

    @model_validator(mode="after")
    def check_is_solved_condition(self) -> Self:
        """Catch edge case where bomb is solved but not marked."""
        if not self.is_solved and all(module.is_solved for module in self.modules):
            self.is_solved = True
        return self
