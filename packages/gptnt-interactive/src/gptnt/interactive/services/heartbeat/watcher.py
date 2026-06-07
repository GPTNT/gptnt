from collections import deque
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from enum import Enum
from time import monotonic
from typing import override

import anyio
import structlog
from coredis import Redis
from pydantic import UUID4, TypeAdapter

from gptnt.core.common.async_ops import Event, periodic
from gptnt.core.ktane.state.game import GameState
from gptnt.interactive.services.heartbeat.base import PlayerState, ReadyState
from gptnt.interactive.services.timeouts import ServiceTimeouts

logger = structlog.get_logger()
service_timeouts = ServiceTimeouts()

# Maximum number of state transitions to keep in the ring buffer
_STATE_HISTORY_MAXLEN = 20


@dataclass
class StateTransition[ServiceStateT: Enum]:
    """Record of a single state transition for diagnostic purposes."""

    timestamp: float
    """Monotonic timestamp of the transition."""

    service_state: ServiceStateT
    ready_state: ReadyState
    heartbeat_seq: int | None = None
    """Sequence number from the heartbeat, if available."""


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
    redis: Redis[str]

    service_state_type: type[ServiceStateT]
    initial_state: ServiceStateT

    ready_state: ReadyState = field(default=ReadyState.ready, init=False)
    _service_state: ServiceStateT = field(init=False)

    update_interval: float = field(
        default=service_timeouts.session_state_watcher_interval, repr=False, init=False
    )

    _interval_changed: Event = field(default_factory=Event, init=False, repr=False)
    """Event for whenever the update interval is changed, to trigger an immediate update."""

    # --- Diagnostic tracking fields ---
    _has_ever_connected: bool = field(default=False, init=False, repr=False)
    """Whether we have ever successfully read a heartbeat from this service."""

    _last_successful_state: ServiceStateT | None = field(default=None, init=False, repr=False)
    """Last known-good service state before a failure."""

    _last_successful_ready_state: ReadyState | None = field(default=None, init=False, repr=False)
    """Last known-good ready state before a failure."""

    _last_successful_update_time: float | None = field(default=None, init=False, repr=False)
    """Monotonic timestamp of the last successful heartbeat read."""

    _last_heartbeat_seq: int | None = field(default=None, init=False, repr=False)
    """Last seen heartbeat sequence number, for detecting gaps."""

    _consecutive_failures: int = field(default=0, init=False, repr=False)
    """Number of consecutive failed heartbeat reads."""

    _state_history: deque[StateTransition[ServiceStateT]] = field(init=False, repr=False)
    """Ring buffer of recent state transitions for post-mortem diagnostics."""

    def __post_init__(self) -> None:
        """Initialize the service state watcher."""
        self._service_state = self.initial_state
        self._state_history = deque(maxlen=_STATE_HISTORY_MAXLEN)

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

    @asynccontextmanager
    async def run_monitor(self) -> AsyncGenerator[None]:
        """Run the service state watcher as a context manager.

        Note: The Redis client lifecycle is managed by the parent component
        (HeartbeatBroadcaster or ExperimentManager), not here.
        """
        async with anyio.create_task_group() as tg:
            tg.start_soon(self.update_service_state_loop)
            logger.debug("Service state watcher started", service_uuid=self.service_uuid)
            try:
                yield
            finally:
                tg.cancel_scope.cancel()
                logger.debug("Service state watcher stopped", service_uuid=self.service_uuid)

    @contextmanager
    def temporary_update_interval(self, interval: float) -> Generator[None]:
        """Temporarily set the update interval to a different value within a context."""
        original_interval = self.update_interval
        self.update_interval = interval
        self._interval_changed.set()
        try:
            yield
        finally:
            self.update_interval = original_interval
            self._interval_changed.set()

    async def update_service_state_loop(self) -> None:
        """Update the service state in a loop."""
        while True:  # noqa: WPS457 (this is not a runaway loop since we break on cancellation)
            with anyio.move_on_after(self.update_interval):
                await self._interval_changed.wait()
            self._interval_changed = Event()
            await self.update_service_state()

    async def update_service_state(self) -> None:
        """Get the current state of the game service from Redis."""
        outputs = await self.redis.hmget(self.redis_key, ["state", "ready_state", "heartbeat_seq"])
        raw_service_state = outputs[0]
        raw_ready_state = outputs[1]
        raw_heartbeat_seq = outputs[2]

        if raw_service_state is None or raw_ready_state is None:
            await self._handle_heartbeat_failure(
                raw_service_state=raw_service_state,
                raw_ready_state=raw_ready_state,
                outputs=outputs,
            )
            return

        # Reset failure tracking on success
        self._consecutive_failures = 0

        # Parse heartbeat_seq if present (for gap detection)
        current_seq: int | None = None
        if raw_heartbeat_seq is not None:
            current_seq = int(raw_heartbeat_seq)
            if self._last_heartbeat_seq is not None and current_seq > self._last_heartbeat_seq + 1:
                missed = current_seq - self._last_heartbeat_seq - 1
                logger.warning(
                    "Heartbeat sequence gap detected",
                    service_name=self.service_name,
                    service_uuid=self.service_uuid,
                    expected_seq=self._last_heartbeat_seq + 1,
                    actual_seq=current_seq,
                    missed_heartbeats=missed,
                )
            self._last_heartbeat_seq = current_seq

        # Update the states
        self._service_state = TypeAdapter(self.service_state_type).validate_python(
            raw_service_state
        )
        self.ready_state = ReadyState(raw_ready_state)

        # Track successful state for diagnostics
        self._has_ever_connected = True
        self._last_successful_state = self._service_state
        self._last_successful_ready_state = self.ready_state
        self._last_successful_update_time = monotonic()

        # Record in state history
        self._state_history.append(
            StateTransition(
                timestamp=monotonic(),
                service_state=self._service_state,
                ready_state=self.ready_state,
                heartbeat_seq=current_seq,
            )
        )

        # Do any additional updating
        await self.update_events_from_states()

    async def update_events_from_states(self) -> None:
        """Update any events that are tied to the service state."""

    async def _handle_heartbeat_failure(  # noqa: WPS231
        self,
        *,
        raw_service_state: str | None,
        raw_ready_state: str | None,
        outputs: tuple[str | None, ...],
    ) -> None:
        """Handle a failed heartbeat read with local-only diagnostic information.

        Logs all locally-tracked state (last good state, consecutive failures, state history)
        without making additional Redis calls. Deeper diagnostics (tombstone lookup, key probing)
        are handled by the registry when it detects the service expiry.
        """
        self._consecutive_failures += 1

        # Compute time since last successful read
        seconds_since_last_success: float | None = None
        if self._last_successful_update_time is not None:
            seconds_since_last_success = round(monotonic() - self._last_successful_update_time, 2)

        # Format state history for logging
        history_summary = TypeAdapter(list[StateTransition[ServiceStateT]]).dump_python(
            list(self._state_history)
        )

        logger.error(
            "Heartbeat read failed — service state unavailable",
            service_name=self.service_name,
            service_uuid=self.service_uuid,
            has_ever_connected=self._has_ever_connected,
            consecutive_failures=self._consecutive_failures,
            # Raw values from Redis
            raw_service_state=raw_service_state,
            raw_ready_state=raw_ready_state,
            outputs=outputs,
            # Last known good state
            last_successful_state=(
                str(self._last_successful_state) if self._last_successful_state else None
            ),
            last_successful_ready_state=(
                self._last_successful_ready_state.value
                if self._last_successful_ready_state
                else None
            ),
            seconds_since_last_success=seconds_since_last_success,
            last_heartbeat_seq=self._last_heartbeat_seq,
            # State history
            recent_state_history=history_summary,
        )

        self.ready_state = ReadyState.not_ready


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

    @override
    @asynccontextmanager
    async def run_monitor(self) -> AsyncGenerator[None]:
        """Lifespan for the game state watcher that runs the monitoring loop in the background.

        We have to override the run_monitor because watching monitoring the game states is a
        blocking thing, since we sit and await for the states to happen.
        """
        async with super().run_monitor(), anyio.create_task_group() as tg:
            tg.start_soon(self.monitor_game_states_loop)
            try:
                yield
            finally:
                tg.cancel_scope.cancel()

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
