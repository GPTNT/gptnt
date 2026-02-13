from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import override

import anyio
import logfire
import structlog
from anyio.abc import TaskGroup
from faststream.redis import RedisBroker
from pydantic import UUID4

from gptnt.common.async_ops import periodic
from gptnt.experiments.experiments import ExperimentSpec
from gptnt.services.events.heartbeat import Heartbeat
from gptnt.services.events.tombstone import ServiceExpiredContext
from gptnt.services.experiment_manager.experiment_runner import ExperimentState
from gptnt.services.experiment_manager.matchmaking import get_playable_pairings
from gptnt.services.experiment_manager.session import Session
from gptnt.services.registry.manifest import (
    GameServiceManifest,
    PlayerServiceManifest,
    ServiceManifest,
    ServiceState,
)
from gptnt.services.registry.registry import ObservableServiceRegistry

logger = structlog.get_logger()


@dataclass(kw_only=True)
class ExperimentManager(ObservableServiceRegistry):
    """Manages experiments and matchmaking."""

    redis_broker: RedisBroker

    specs: set[ExperimentSpec] = field(default_factory=set, init=False)
    _sessions: set[Session] = field(default_factory=set, init=False, repr=False)
    _lifespan_task_group: TaskGroup | None = field(default=None, init=False, repr=False)

    @override
    @asynccontextmanager
    async def lifespan(self) -> AsyncGenerator[None]:
        """Lifespan for the experiment manager."""
        async with self.redis_broker, super().lifespan(), anyio.create_task_group() as tg:
            self._lifespan_task_group = tg
            tg.start_soon(self._matchmaking_loop)
            tg.start_soon(self.metrics_loop)

            logger.info("EM is running")
            try:  # noqa: WPS243
                yield
            finally:
                self._lifespan_task_group = None
                logger.info("EM is shutting down")
                tg.cancel_scope.cancel()

    @logfire.instrument("Start Experiment")
    async def start_experiment(
        self,
        *,
        spec: ExperimentSpec,
        game: GameServiceManifest,
        defuser: PlayerServiceManifest,
        expert: PlayerServiceManifest | None,
    ) -> None:
        """Start an experiment."""
        if self._lifespan_task_group is None:
            logger.error("Cannot start experiment: EM lifespan task group is not running")
            return

        with logfire.span("Create session"):
            session = Session(
                game=game,
                defuser=defuser,
                expert=expert,
                spec=spec,
                redis=self.redis,
                redis_broker=self.redis_broker,
            )
            self._sessions.add(session)
            for uuid in session.service_uuids:
                self.connected_services[uuid].state = ServiceState.in_experiment

        self._lifespan_task_group.start_soon(session.run)

    async def cleanup_finished_sessions(self) -> None:
        """Check for finished sessions and clean them up."""
        finished_sessions = [
            session for session in self._sessions if session.state == ExperimentState.done
        ]
        if not finished_sessions:
            return

        # Cleanup all the finished sessions concurrently
        async with anyio.create_task_group() as tg:
            for session in finished_sessions:
                if session.is_hard_crash:
                    self.failed_experiments_counter.add(1)
                else:
                    self.completed_experiments_counter.add(1)
                tg.start_soon(session.cleanup)

        self._sessions.difference_update(finished_sessions)
        for session in finished_sessions:
            logger.debug("Room removed from running sessions", experiment=session.name)

    @override
    async def _handle_expired_service(
        self,
        service_uuid: UUID4,
        service: ServiceManifest[Heartbeat],
        context: ServiceExpiredContext,
    ) -> None:
        """Handle service expiring by stopping any running experiments."""
        previous_state = service.state

        # Set it to not ready
        service.state = ServiceState.not_ready
        logger.debug(
            "Service has expired",
            service_uuid=service_uuid,
            service_type=service.service_type,
            failure_category=context.failure_category.value,
            tombstone=context.tombstone.model_dump() if context.tombstone else None,
            heartbeat_key_exists=context.heartbeat_key_exists,
            heartbeat_key_ttl=context.heartbeat_key_ttl,
            last_heartbeat_seq=context.last_heartbeat_seq,
            last_uptime_seconds=context.last_uptime_seconds,
            last_pid=context.last_pid,
            last_hostname=context.last_hostname,
        )

        if previous_state == ServiceState.in_experiment:
            if session := self._find_session_by_service_uuid(service_uuid):
                await session.force_stop_experiment()
            else:
                logger.warning(
                    "No running session found for disconnected service", service=service
                )

    async def _matchmaking_loop(self, *, interval: float = 1) -> None:
        """Continuously attempt to match experiments."""
        async for _ in periodic(interval):
            await self._try_match_experiments()
            await self.cleanup_finished_sessions()

    def _find_session_by_service_uuid(self, service_uuid: UUID4) -> Session | None:
        """Find an experiment by service UUID."""
        session = iter(exp for exp in self._sessions if service_uuid in exp.service_uuids)
        if not (session := next(session, None)):
            return None
        return session

    async def _try_match_experiments(self) -> None:
        """Try to match available resources into experiments."""
        # Get available resources
        ready_players = self.ready_players
        ready_games = self.ready_games
        with logfire.suppress_instrumentation():
            logger.debug(
                "Trying to match experiments",
                ready_players=len(ready_players),
                ready_games=len(ready_games),
                running_sessions=len(self._sessions),
            )
        if not ready_games:
            return  # Need at least one game

        # Find possible pairings
        playable_pairings = get_playable_pairings(
            available_players=ready_players, available_experiments=list(self.specs)
        )

        for pairing in playable_pairings:
            if not ready_games:
                break  # Resources exhausted

            game = ready_games.pop()
            self.specs.remove(pairing.experiment)

            await self.start_experiment(  # noqa: WPS476
                spec=pairing.experiment, game=game, defuser=pairing.defuser, expert=pairing.expert
            )
            _ = await anyio.sleep(1)  # noqa: WPS476

    @override
    def _update_all_metrics(self) -> None:
        """Update all Logfire metrics."""
        super()._update_all_metrics()
        self.available_experiments_gauge.set(len(self.specs))
        self.running_experiments_gauge.set(
            len([session for session in self._sessions if session.state < ExperimentState.done])
        )
