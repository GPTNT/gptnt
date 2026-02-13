from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import cast, override

import anyio
from anyio.abc import TaskGroup
from coredis import Redis
from pydantic import UUID4, TypeAdapter
from structlog import get_logger

from gptnt.common.async_ops import periodic
from gptnt.ktane.state.game import GameState
from gptnt.services.events.heartbeat import GameHeartbeat, Heartbeat, PlayerHeartbeat
from gptnt.services.events.player import PlayerState
from gptnt.services.events.tombstone import ServiceExpiredContext
from gptnt.services.registry.manifest import ServiceManifest, ServiceState
from gptnt.services.registry.metrics import LogfireGauge
from gptnt.services.timeouts import ServiceTimeouts

logger = get_logger()
timeouts = ServiceTimeouts()


@dataclass(kw_only=True)
class ServiceRegistry:
    """Registry for all connected services."""

    redis: Redis[str]

    connected_services: dict[UUID4, ServiceManifest[Heartbeat]] = field(default_factory=dict)

    _watchdog_task_group: TaskGroup | None = field(default=None, init=False)

    @property
    def ready_players(self) -> list[ServiceManifest[PlayerHeartbeat]]:
        """List of all connected and ready players."""
        player_manifests = [
            service
            for service in self.connected_services.values()
            if service.is_ready
            and service.state == ServiceState.idle
            and isinstance(service.heartbeat, PlayerHeartbeat)
            and service.heartbeat.state == PlayerState.idle
        ]
        return cast("list[ServiceManifest[PlayerHeartbeat]]", player_manifests)

    @property
    def ready_games(self) -> list[ServiceManifest[GameHeartbeat]]:
        """List of all connected and ready game instances."""
        game_manifests = [
            service
            for service in self.connected_services.values()
            if service.is_ready
            and service.state == ServiceState.idle
            and isinstance(service.heartbeat, GameHeartbeat)
            and service.heartbeat.state == GameState.main_menu
        ]
        return cast("list[ServiceManifest[GameHeartbeat]]", game_manifests)

    @asynccontextmanager
    async def lifespan(self) -> AsyncGenerator[None]:
        """Lifespan with watchdog nursery management."""
        async with self.redis, anyio.create_task_group() as watchdog_task_group:
            watchdog_task_group.start_soon(self.process_heartbeat_loop)
            self._watchdog_task_group = watchdog_task_group
            try:  # noqa: WPS243
                yield
            finally:
                logger.info("Shutting down service manager")
                watchdog_task_group.cancel_scope.cancel()
                self._watchdog_task_group = None

    async def process_heartbeat_loop(self) -> None:
        """Continually process heartbeats."""
        with anyio.CancelScope():
            async for _ in periodic(timeouts.heartbeat_check_interval):
                # Pull the heartbeats from Redis and update the service states
                await self.update_heartbeats()
                # Check for expired or not-ready services
                await self.check_for_expired_services()

    async def update_heartbeats(self) -> None:
        """Check all the heartbeats and update the service state."""
        heartbeat_map = await self._pull_heartbeats()
        # Update existing services
        for uuid, heartbeat in heartbeat_map.items():
            if uuid in self.connected_services:
                self.connected_services[uuid].heartbeat = heartbeat
            else:
                # If the service is not in the registry, add it
                self.connected_services[uuid] = ServiceManifest(heartbeat=heartbeat)
                logger.info("New service connected", service=self.connected_services[uuid])

    async def check_for_expired_services(self) -> None:
        """Check for expired services and handle them."""
        expired_services = [
            (uuid, service)
            for uuid, service in self.connected_services.items()
            if service.is_expired
        ]
        if not expired_services:
            return

        async with anyio.create_task_group() as tg:
            for uuid, service in expired_services:
                tg.start_soon(self._expire_service, uuid, service)
                del self.connected_services[uuid]  # noqa: WPS420

    async def _expire_service(
        self, service_uuid: UUID4, service: ServiceManifest[Heartbeat]
    ) -> None:
        """Build diagnostic context for an expired service and handle it."""
        context = ServiceExpiredContext.model_validate(
            {
                "service_uuid": service_uuid,
                "service_type": service.service_type,
                "tombstone": await self.redis.hgetall(service.tombstone_key),
                "heartbeat_key_exists": bool(await self.redis.exists([service.heartbeat_key])),
                "heartbeat_key_ttl": await self.redis.ttl(service.heartbeat_key),
                "remaining_heartbeat_fields": await self.redis.hgetall(service.heartbeat_key),
                # Extract from the last known heartbeat in the manifest
                "last_heartbeat_seq": service.heartbeat.heartbeat_seq,
                "last_uptime_seconds": service.heartbeat.uptime_seconds,
                "last_pid": service.heartbeat.pid,
                "last_hostname": service.heartbeat.hostname,
            }
        )
        await self._handle_expired_service(service_uuid, service, context)

    async def _handle_expired_service(
        self,
        service_uuid: UUID4,
        service: ServiceManifest[Heartbeat],
        context: ServiceExpiredContext,
    ) -> None:
        """Handle a service that has expired."""
        raise NotImplementedError

    async def _pull_heartbeats(self) -> dict[UUID4, Heartbeat]:
        """Pull all the heartbeats from Redis."""
        heartbeat_keys = [
            heartbeat_key async for heartbeat_key in self.redis.scan_iter(match="heartbeat:*")
        ]

        # Use a pipeline to fetch all heartbeats in one go
        async with self.redis.pipeline() as pipeline:
            _ = [pipeline.hgetall(key) for key in heartbeat_keys]
        raw_heartbeats = pipeline.results  # noqa: WPS441

        if not raw_heartbeats:
            return {}

        heartbeats = TypeAdapter(list[Heartbeat]).validate_python(raw_heartbeats)
        # convert them to a uuid-heartbeat mapping
        heartbeat_map = {hb.uuid: hb for hb in heartbeats}
        # logger.debug("Pulled heartbeats from Redis", heartbeat_map=heartbeat_map)
        return heartbeat_map


@dataclass(kw_only=True)
class ObservableServiceRegistry(ServiceRegistry, LogfireGauge):
    """Service registry that has metrics and observability."""

    @override
    def _update_all_metrics(self) -> None:  # noqa: WPS213
        """Update the Logfire gauges with the current counts."""
        games = [
            service
            for service in self.connected_services.values()
            if isinstance(service.heartbeat, GameHeartbeat)
        ]
        players = [
            service
            for service in self.connected_services.values()
            if isinstance(service.heartbeat, PlayerHeartbeat)
        ]

        self.connected_players_gauge.set(len(players))
        self.connected_games_gauge.set(len(games))

        self.available_players_gauge.set(
            len([player for player in players if player.state == ServiceState.idle])
        )
        self.available_games_gauge.set(
            len([game for game in games if game.state == ServiceState.idle])
        )

        self.cleanup_games_gauge.set(
            len([game for game in games if game.is_not_ready or game.is_expired])
        )
        self.cleanup_players_gauge.set(
            len([player for player in players if player.is_not_ready or player.is_expired])
        )

        self.running_players_gauge.set(
            len([player for player in players if player.state == ServiceState.in_experiment])
        )
        self.running_games_gauge.set(
            len([game for game in games if game.state == ServiceState.in_experiment])
        )
