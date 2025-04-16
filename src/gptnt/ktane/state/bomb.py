from pydantic import BaseModel, ConfigDict, NonNegativeFloat, alias_generators, with_config

from gptnt.ktane.state.modules import ModuleStates
from gptnt.ktane.state.widget import WidgetStates


@with_config(ConfigDict(alias_generator=alias_generators.to_snake, populate_by_name=True))
class BombState(BaseModel):
    """State of the bomb at the current timestep."""

    seed: int
    time_remaining: NonNegativeFloat = 300
    timestamp: NonNegativeFloat
    max_strikes: int = 3
    current_strikes: int = 0
    is_detonated: bool
    is_solved: bool
    widgets: list[WidgetStates]
    modules: list[ModuleStates]
