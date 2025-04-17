from pydantic import BaseModel, ConfigDict, NonNegativeFloat, alias_generators

from gptnt.ktane.state.modules import ModuleStates, TimerState
from gptnt.ktane.state.widget import WidgetStates


class BombState(BaseModel):
    """State of the bomb at the current timestep."""

    model_config = ConfigDict(alias_generator=alias_generators.to_camel, populate_by_name=True)

    seed: int
    timestamp: NonNegativeFloat
    max_strikes: int = 3
    current_strikes: int = 0
    is_detonated: bool
    is_solved: bool
    is_light_on: bool
    timer_module: TimerState
    widgets: list[WidgetStates]
    modules: list[ModuleStates]
