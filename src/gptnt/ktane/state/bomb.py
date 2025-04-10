from pydantic import BaseModel, NonNegativeFloat

from gptnt.ktane.state.modules import ModuleStates
from gptnt.ktane.state.widget import WidgetStates


class BombState(BaseModel):
    """State of the bomb at the current timestep."""

    seed: int
    time_remaining: int = 300
    timestamp: NonNegativeFloat
    max_strikes: int = 3
    current_strikes: int = 0
    serial_number: str
    widgets: list[WidgetStates]
    modules: list[ModuleStates]
