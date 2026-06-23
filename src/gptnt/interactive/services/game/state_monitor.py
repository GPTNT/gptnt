from dataclasses import dataclass, field

import aiohttp
import logfire
import structlog
from httpx import HTTPError

from gptnt.common.async_ops import AsyncValue, Event, periodic
from gptnt.interactive.services.timeouts import ServiceTimeouts
from gptnt.ktane.client import KtaneClient
from gptnt.ktane.process_manager import GameProcessManager
from gptnt.ktane.state.game import GameState

logger = structlog.get_logger()
service_timeouts = ServiceTimeouts()


@dataclass(kw_only=True)
class GameStateMonitor:
    """Monitors and tracks game state changes."""

    client: KtaneClient
    state: AsyncValue[GameState] = field(
        default_factory=lambda: AsyncValue(initial_value=GameState.unknown)
    )
    ready_event: Event = field(default_factory=Event, init=False)
    first_lights_on: Event = field(default_factory=Event, init=False)
    """Event set when the game has had its first lights on."""

    first_lights_off: Event = field(default_factory=Event, init=False)
    """Event set when the game has had its first lights off."""

    history: list[GameState] = field(default_factory=list, init=False)
    """History of game states for debugging purposes."""

    @property
    def is_ready(self) -> bool:
        """Check if game has reached ready state."""
        return self.ready_event.is_set()

    @property
    def is_expected_death(self) -> bool:
        """Check if the game is expected to be dead.

        Note that we can be in "unknown" when the game is in the middle of restarting from
        previously terminated, which means that the latest state that came in was unknown. This is
        a weird lil edge case that happens because terminating is separate to the exception
        handling
        """
        return (
            self.state.value in {GameState.game_ended, GameState.transitioning, GameState.unknown}
            and self.first_lights_on.is_set()
            and self.ready_event.is_set()
        )

    async def wait_for_ready(self) -> None:
        """Wait for game to be ready."""
        await self.ready_event.wait()

    def reset(self) -> None:
        """Reset the monitor state."""
        self.state.value = GameState.unknown
        self.ready_event = Event()
        self.first_lights_on = Event()
        self.first_lights_off = Event()
        self.history.clear()
        logger.info("Game state monitor reset")

    async def monitor(
        self,
        process_manager: GameProcessManager,
        *,
        interval: float = service_timeouts.game_state_interval,
    ) -> None:
        """Monitor game state until cancelled."""
        async for _ in periodic(interval):
            if process_manager.is_alive:
                await self._poll_game_state_once()

    async def _poll_game_state_once(self) -> None:
        """Poll the game state once, tolerating transient transport errors."""
        try:
            await self._check_game_state()
        except (HTTPError, aiohttp.ClientError):
            if self.history:
                logger.debug("Failed to get game state?", history=self.history)
            else:
                logger.debug("Waiting for game to start (no history yet)", history=self.history)
        except Exception:
            # Anything other than a transient transport error is unexpected and would otherwise
            # be silently absorbed by the surrounding task group on teardown.
            logger.exception("Unexpected error while polling game state")
            raise

    async def _check_game_state(self) -> None:
        with logfire.suppress_instrumentation():
            new_state = await self.client.get_game_state()

        if new_state != self.state.value:
            logger.info(
                f"Game state changed: {self.state.value} -> {new_state}",
                from_state=self.state.value,
                to_state=new_state,
            )
            self.state.value = new_state
            self.history.append(new_state)

        actions = {
            GameState.main_menu: self._on_main_menu,
            GameState.lights_on: self._on_lights_on,
            GameState.lights_off: self._on_lights_off,
        }

        action_to_perform = actions.get(new_state)
        if action_to_perform:
            action_to_perform()

    def _on_main_menu(self) -> None:
        if not self.is_ready:
            self.ready_event.set()

    def _on_lights_on(self) -> None:
        if not self.first_lights_on.is_set():
            self.first_lights_on.set()

    def _on_lights_off(self) -> None:
        if not self.first_lights_off.is_set():
            self.first_lights_off.set()
