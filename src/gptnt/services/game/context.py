from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from functools import partial
from typing import override

import anyio
import structlog

from gptnt.common.async_ops import periodic
from gptnt.ktane.client import KtaneClient
from gptnt.services.events.heartbeat import GameHeartbeat
from gptnt.services.game.process_manager import GameProcessManager
from gptnt.services.game.state_monitor import GameStateMonitor
from gptnt.services.heartbeat_broadcaster import HeartbeatBroadcaster
from gptnt.services.timeouts import ServiceTimeouts

logger = structlog.get_logger()
service_timeouts = ServiceTimeouts()


class GameProcessDiedError(Exception):
    """Exception indicating the game process has died."""


@dataclass(kw_only=True)
class GameServiceContext(HeartbeatBroadcaster):
    """Run a single instance of a game."""

    service_name: str = "game"
    process_manager: GameProcessManager = field(default_factory=GameProcessManager, init=False)
    state_monitor: GameStateMonitor = field(init=False)
    ktane_client: KtaneClient = field(default_factory=partial(KtaneClient, url=""), init=False)

    def __post_init__(self) -> None:
        """Setup components and subscriptions."""
        self.state_monitor = GameStateMonitor(client=self.ktane_client)

    @override
    def heartbeat_event(self) -> GameHeartbeat:
        """Create the connect event for this service that gets sent on start."""
        return GameHeartbeat(
            uuid=self.uuid,
            service_name=self.service_name,
            state=self.state_monitor.state.value,
            ready_state=self.ready_state,
            ktane_url=str(self.ktane_client.base_url),
        )

    @override
    @asynccontextmanager
    async def lifespan(self) -> AsyncGenerator[None]:
        """Lifespan for the Game Instance."""
        async with super().lifespan(), anyio.create_task_group() as tg:
            tg.start_soon(self._game_supervisor)
            try:
                yield
            finally:
                await self.process_manager.terminate()
                tg.cancel_scope.cancel()

    async def _game_supervisor(self) -> None:
        """Supervise the game, restarting if needed."""
        while True:
            try:
                await self._run_game_session()
            except* GameProcessDiedError:
                logger.debug("Game process died, restarting")
                if not self.state_monitor.is_expected_death:
                    logger.exception("Game died unexpectedly", history=self.state_monitor.history)
                    self.ready_state = self.ready_state.not_ready
                self.state_monitor.reset()

    async def _run_game_session(self) -> None:  # noqa: WPS213
        """Run a single game session."""
        async with anyio.create_task_group() as tg:
            # Start the game process
            port = await self.process_manager.start()
            await self.ktane_client.update_url(f"http://localhost:{port}")

            # Start monitoring
            logger.debug("Starting game state monitor")
            tg.start_soon(self.state_monitor.monitor, self.process_manager)

            # Wait for ready
            logger.debug("Waiting for game to be ready")
            await self.state_monitor.wait_for_ready()
            self.ready_state = self.ready_state.ready

            # Monitor for death
            logger.debug("Starting process death monitor")
            tg.start_soon(self._monitor_process_death)

            # Run until cancelled
            # Note that we are suppressing the CancelledError exception that gets raised here
            # because we don't need to know about it. When the game dies, we will get a
            # GameProcessDiedError, and when we are exiting the service, we will catch it in the
            # lifespan
            with suppress(anyio.get_cancelled_exc_class()):
                logger.debug("Game session running, waiting indefinitely")
                await anyio.sleep_forever()

    async def _monitor_process_death(self) -> None:
        """Monitor for process death."""
        with anyio.CancelScope():
            async for _ in periodic(1):
                if not self.process_manager.is_alive:
                    raise GameProcessDiedError("Game exited")
