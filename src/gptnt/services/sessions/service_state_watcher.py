from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import cast, override

import anyio
import structlog
from pydantic import UUID4, TypeAdapter
from redis_anyio import RedisClient

from gptnt.common.async_ops import Event, periodic
from gptnt.ktane.state.game import GameState
from gptnt.services.events.heartbeat import ReadyState
from gptnt.services.events.player import PlayerState
from gptnt.services.timeouts import ServiceTimeouts

logger = structlog.get_logger()
service_timeouts = ServiceTimeouts()


@dataclass(kw_only=True)
class BaseServiceStateWatcher[ServiceStateT: Enum]:
    """Base service state watcher that polls the heartbeats from Redis.

    While this is more code and a bit more confused to follow along with, this is preferable to
    constantly sending requests to the API itself since that is going to block up the thread and
    slow things down for the game. When you have a LOT of services all pinging at once, this can
    add up and lead to a thundering herd, so let's just avoid that.
    """

    service_name: str
    service_uuid: UUID4
    redis: RedisClient = field(default_factory=RedisClient)

    service_state_type: type[ServiceStateT]
    initial_state: ServiceStateT

    ready_state: ReadyState = field(default=ReadyState.ready, init=False)
    _service_state: ServiceStateT = field(init=False)

    update_interval: float = field(
        default=service_timeouts.session_state_watcher_interval, repr=False, init=False
    )

    def __post_init__(self) -> None:
        """Initialize the service state watcher."""
        self._service_state = self.initial_state

    @property
    def state(self) -> ServiceStateT:
        """Get the current player state."""
        return self._service_state

    @property
    def redis_key(self) -> str:
        """Get the key for the state in Redis."""
        return f"heartbeat:{self.service_name}:{self.service_uuid}"

    @property
    def is_hard_crash(self) -> bool:
        """Check if the service has hard crashed."""
        return self.ready_state == ReadyState.not_ready

    @property
    def is_ready(self) -> bool:
        """Check if the service is ready."""
        return self.ready_state == ReadyState.ready

    def reset_update_interval(self) -> None:
        """Reset the update interval to the default value."""
        self.update_interval = service_timeouts.session_state_watcher_interval

    @asynccontextmanager
    async def run_monitor(self) -> AsyncGenerator[None]:
        """Run the service state watcher as a context manager."""
        async with self.redis, anyio.create_task_group() as tg:
            tg.start_soon(self.update_service_state_loop)
            logger.debug("Service state watcher started", service_uuid=self.service_uuid)
            try:
                yield
            finally:
                tg.cancel_scope.cancel()
                logger.debug("Service state watcher stopped", service_uuid=self.service_uuid)

    async def update_service_state_loop(self) -> None:
        """Update the service state in a loop."""
        logger.debug("Starting service state update loop", service_uuid=self.service_uuid)
        async for _ in periodic(self.update_interval):
            await self.update_service_state()
        logger.debug("Service state update loop stopped", service_uuid=self.service_uuid)

    async def update_service_state(self) -> None:
        """Get the current state of the game service from Redis."""
        outputs = await self.redis.hmget(self.redis_key, "state", "ready_state")
        outputs = cast("list[str | None]", outputs)
        # logger.debug("Results from Redis", redis_key=self.redis_key, outputs=outputs)
        raw_service_state = outputs[0]
        raw_ready_state = outputs[1]

        if raw_service_state is None or raw_ready_state is None:
            logger.exception(
                "Service state or ready state is None, cannot update",
                service_uuid=self.service_uuid,
                raw_service_state=raw_service_state,
                raw_ready_state=raw_ready_state,
            )
            self.ready_state = ReadyState.not_ready
            # Return so that we don't try to update the state since it is invalid and will throw
            # and crash the EM
            return

        # Update the states
        self._service_state = TypeAdapter(self.service_state_type).validate_python(
            raw_service_state
        )
        self.ready_state = ReadyState(raw_ready_state)

        # Do any additional updating
        await self.update_events_from_states()

    async def update_events_from_states(self) -> None:
        """Update any events that are tied to the service state."""


@dataclass(kw_only=True)
class PlayerStateWatcher(BaseServiceStateWatcher[PlayerState]):
    """Watch the player state by polling the heartbeats from Redis."""

    service_state_type: type[PlayerState] = PlayerState
    initial_state: PlayerState = field(default=PlayerState.idle, init=False)

    is_first_waiting_for_turn: Event = field(default_factory=Event, init=False)
    is_stopping: Event = field(default_factory=Event, init=False)

    @override
    async def update_events_from_states(self) -> None:
        if self._service_state == PlayerState.waiting_for_turn:
            self.is_first_waiting_for_turn.set()

        if self._service_state >= PlayerState.stopping:
            self.is_stopping.set()

    async def wait_for_waiting_for_turn(
        self,
        *,
        fail_after: float = service_timeouts.configure_services_timeout,
        interval: float = service_timeouts.session_state_watcher_interval,
    ) -> None:
        """Wait for the player to be in a waiting for turn state."""
        with anyio.fail_after(fail_after):
            async for _ in periodic(interval):
                if self._service_state == PlayerState.waiting_for_turn:
                    return


@dataclass(kw_only=True)
class GameStateWatcher(BaseServiceStateWatcher[GameState]):
    """Watch the game state by polling the heartbeats.

    While this is more code and a bit more confused to follow along with, this is preferable to
    constantly sending requests to the API itself since that is going to block up the thread and
    slow things down for the game. When you have a LOT of services all pinging at once, this can
    add up and lead to a thundering herd, so let's just avoid that.
    """

    service_state_type: type[GameState] = GameState
    initial_state: GameState = field(default=GameState.unknown, init=False)

    lights_are_off_event: Event = field(default_factory=Event, init=False)
    """Event to signal that the game is ready to begin, when the game is in a lights off state."""
    first_lights_on_event: Event = field(default_factory=Event, init=False)
    """Event to signal that the game has started (and lights are first on)."""
    good_game_over_event: Event = field(default_factory=Event, init=False)
    """Event to signal that the game finished without any errors or issues."""

    @property
    def is_game_over(self) -> bool:
        """Check if the game is over."""
        return self.good_game_over_event.is_set() or self.is_hard_crash

    @asynccontextmanager
    async def run_monitor(self) -> AsyncGenerator[None]:
        """Run the game state watcher as a context manager."""
        async with super().run_monitor(), anyio.create_task_group() as tg:
            tg.start_soon(self.monitor_game_states_loop)
            try:
                yield
            finally:
                tg.cancel_scope.cancel()
                logger.debug("Game state watcher cancelled", game_uuid=self.service_uuid)

    async def monitor_game_states_loop(self) -> None:
        """Monitor for the game state changes in a loop.

        This helps in defining the lifecycle of the game, mainly the first time the lights are on
        """
        # Block until the game is in the first lights off state
        await self.wait_for_first_lights_off()
        # Block until the game is in a lights on state
        await self.wait_for_lights_on()
        logger.debug("Game is in lights on state", game_uuid=self.service_uuid)
        # Block until the game is over
        await self.wait_for_game_over()

    async def wait_for_first_lights_off(
        self, *, fail_after: float = service_timeouts.maximum_experiment_duration
    ) -> None:
        """Wait for the game to be in a lights off state."""
        with anyio.fail_after(fail_after):
            logger.debug("Waiting for lights off", game_uuid=self.service_uuid)
            while not self.lights_are_off_event.is_set():
                if self._service_state == GameState.lights_off:
                    self.lights_are_off_event.set()
                    logger.debug("Game is ready to begin", game_uuid=self.service_uuid)
                await anyio.sleep(self.update_interval)

    async def wait_for_lights_on(
        self, *, fail_after: float = service_timeouts.maximum_experiment_duration
    ) -> None:
        """Wait for the game to be in a lights on state."""
        with anyio.fail_after(fail_after):
            logger.debug("Waiting for lights on", game_uuid=self.service_uuid)
            while not self.first_lights_on_event.is_set():
                if self._service_state == GameState.lights_on:
                    self.first_lights_on_event.set()
                    logger.debug("Game has started", game_uuid=self.service_uuid)
                await anyio.sleep(self.update_interval)

    async def wait_for_game_over(
        self, *, fail_after: float = service_timeouts.maximum_experiment_duration
    ) -> None:
        """Wait for the game to be over."""
        with anyio.fail_after(fail_after):
            logger.debug("Waiting for game over", game_uuid=self.service_uuid)
            while not self.is_game_over:
                if self._service_state in {GameState.game_ended, GameState.transitioning}:
                    logger.debug("Game has ended successfully", game_uuid=self.service_uuid)
                    self.good_game_over_event.set()
                await anyio.sleep(self.update_interval)
