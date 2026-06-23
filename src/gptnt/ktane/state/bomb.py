import json
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

from gptnt.ktane.state.modules import (
    NEEDS_MULTIPLE_IMAGES,
    KtaneComponent,
    ModuleStates,
    TimerState,
)
from gptnt.ktane.state.widget import WidgetStates


def _serialise_states_to_string(
    input_value: Any,
    handler: SerializerFunctionWrapHandler,  # noqa: WPS110
    info: SerializationInfo,  # noqa: WPS110
    *,
    obj_type: type,
) -> str:
    """Either we serialize it to string or let the handler do its job."""
    if info.context and info.context.get("serialize_as_string", False):
        return json.dumps(TypeAdapter(obj_type).dump_python(input_value, mode="json"))
    return handler(input_value)


def _validate_state_from_string(data: str | Any) -> dict[str, Any]:
    """Validate state from string or pass through."""
    if isinstance(data, str):
        return orjson.loads(data)
    return data


class BombState(BaseModel):
    """State of the bomb at the current timestep."""

    model_config = ConfigDict(alias_generator=alias_generators.to_camel, populate_by_name=True)

    seed: int
    max_strikes: int = 3
    strikes: (
        Annotated[
            list[KtaneComponent],
            BeforeValidator(_validate_state_from_string),
            WrapSerializer(
                partial(_serialise_states_to_string, obj_type=list[KtaneComponent]),
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
    def module_names(self) -> list[KtaneComponent]:
        """Get the names of all modules on the bomb."""
        return [module.name for module in self.modules]

    @property
    def seconds_remaining(self) -> float:
        """Get the remaining time on the bomb."""
        return self.timer_module.seconds_remaining

    @property
    def zoomed_in_component(self) -> KtaneComponent | None:
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
            return NEEDS_MULTIPLE_IMAGES.get(self.zoomed_in_component, False)
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
    def current_strikes(self) -> int:
        """Get the current number of strikes."""
        if not self.strikes:
            return 0
        return len(self.strikes)

    @property
    def is_game_correctly_over(self) -> bool:
        """Check if the game is correctly over."""
        return self.is_detonated or self.is_solved or self.is_timed_out or self.is_strike_out

    @model_validator(mode="after")
    def check_is_solved_condition(self) -> Self:
        """Catch edge case where bomb is solved but not marked."""
        if not self.is_solved and all(module.is_solved for module in self.modules):
            self.is_solved = True
        return self
