from pydantic import BaseModel, ConfigDict, alias_generators

from gptnt.ktane.state.modules import KtaneComponent, ModuleStates, TimerState
from gptnt.ktane.state.widget import WidgetStates


class BombState(BaseModel):
    """State of the bomb at the current timestep."""

    model_config = ConfigDict(alias_generator=alias_generators.to_camel, populate_by_name=True)

    seed: int
    max_strikes: int = 3
    current_strikes: int = 0
    strikes: list[KtaneComponent] | None
    is_detonated: bool
    is_solved: bool
    is_light_on: bool
    bomb_side: str
    timer_module: TimerState
    widgets: list[WidgetStates]
    modules: list[ModuleStates]

    @property
    def zoomed_in_component(self) -> KtaneComponent | None:
        """Get the currently zoomed in component, if we are zoomed in."""
        for module in self.modules:
            if module.in_focus:
                return module.name
        return None

    @property
    def is_timed_out(self) -> bool:
        """Check if the bomb is timed out."""
        return self.timer_module.seconds_remaining <= 0

    @property
    def is_strike_out(self) -> bool:
        """Check if the bomb is strike out."""
        return self.current_strikes >= self.max_strikes

    @property
    def is_game_correctly_over(self) -> bool:
        """Check if the game is correctly over."""
        return self.is_detonated or self.is_solved or self.is_timed_out or self.is_strike_out
