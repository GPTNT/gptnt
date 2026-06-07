from typing import override

from gptnt.core.ktane.state.game import GameState
from gptnt.interactive.services.heartbeat.base import BaseHeartbeat


class GameHeartbeat(BaseHeartbeat, frozen=True):
    """Event for a game service to indicate that it is alive and well."""

    state: GameState
    ktane_url: str
    """Current URL for the game itself."""

    @property
    @override
    def is_idle(self) -> bool:
        """Check if the game is in an idle state."""
        return self.state == GameState.main_menu and super().is_idle
