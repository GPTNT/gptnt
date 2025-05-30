from contextlib import suppress
from dataclasses import dataclass, field
from types import TracebackType
from typing import overload, override

import logfire
from pydantic.types import UUID4
from structlog import get_logger

from gptnt.api.base_rabbitmq_client import BaseRabbitMQClient, ExceptionUnhandledError
from gptnt.api.commands import StartExperimentCommand, StopExperimentCommand
from gptnt.api.events import (
    ConnectEvent,
    ExperimentDoneEvent,
    GameConnectEvent,
    HeartbeatEvent,
    NotReadyEvent,
    PlayerConnectEvent,
    ReadinessEvent,
    ReadyEvent,
    RoomConnectEvent,
)
from gptnt.api.experiment_manager.experiment_bindings import remove_experiment_bindings
from gptnt.api.experiment_manager.experiment_descriptor import ExperimentDescriptor
from gptnt.api.experiment_manager.heartbeat_watchdog import (
    HeartbeatWatchdog,
    HeartbeatWatchdogTriggeredError,
)
from gptnt.api.experiment_manager.metrics import LogfireGauge
from gptnt.api.experiment_manager.structures import ConnectedPlayerService, ConnectedService
from gptnt.api.experiment_manager.tinder import get_playable_pairings
from gptnt.common.async_ops import busy_wait_interval
from gptnt.experiments.experiments import ExperimentSpec

logger = get_logger()


@dataclass(kw_only=True)
class ExperimentManager(BaseRabbitMQClient):
    """Manages connections and matchmaking."""

    connected_services: dict[UUID4, ConnectedService] = field(default_factory=dict, init=False)
    running_experiments: set[ExperimentDescriptor] = field(default_factory=set, init=False)
    specs: set[ExperimentSpec] = field(default_factory=set, init=False)

    def __post_init__(self) -> None:
        """Synchronous startup logic to run BEFORE app start."""
        super().__post_init__()

        self.api_queues.experiment_heartbeat().subscribe(self.handle_heartbeat)
        self.api_queues.experiment_connections().subscribe(self.handle_connection)
        self.api_queues.experiment_ready().subscribe(self.handle_ready)
        self.api_queues.experiment_specs().subscribe(self.handle_new_spec)

    @property
    def ready_players(self) -> list[ConnectedPlayerService]:
        """List of all connected and ready players."""
        count = self._filter_ready_services_by_type(connection_type=PlayerConnectEvent)
        # logger.debug(f"Ready players: {len(count)}")
        LogfireGauge.available_players.set(len(count))
        return count

    @property
    def ready_games(self) -> list[ConnectedService]:
        """List of all connected and ready game instances."""
        count = self._filter_ready_services_by_type(connection_type=GameConnectEvent)
        # logger.debug(f"Ready games: {len(count)}")
        LogfireGauge.available_games.set(len(count))
        return count

    @property
    def ready_rooms(self) -> list[ConnectedService]:
        """List of all connected and ready room instances."""
        count = self._filter_ready_services_by_type(connection_type=RoomConnectEvent)
        # logger.debug(f"Ready rooms: {len(count)}")
        LogfireGauge.available_rooms.set(len(count))
        return count

    @override
    async def lifespan_setup(self) -> None:
        """Asynchronous logic to run after app startup."""
        logger.info("Started Experiment Manager")
        _ = self.background_tasks.create_task(self.matchmaking_loop())

    @override
    async def lifespan_cleanup(self) -> None:
        """Asynchronous logic to run during app shutdown."""
        logger.info("Stopped Experiment Manager")

    @override
    async def handle_background_task_exception(
        self,
        exc_type: type[BaseException] | None = None,
        exc_obj: BaseException | None = None,
        exc_tb: TracebackType | None = None,
    ) -> None:
        """Handle uncaught exceptions from background_tasks."""
        # Leave the error for parent to handle
        if isinstance(exc_obj, HeartbeatWatchdogTriggeredError):
            logger.warning(
                f"Service disconnected, UUID: {exc_obj.uuid}", metadata=exc_obj.metadata
            )
            self.connected_services[exc_obj.uuid].is_ready = False

            # Stop the experiment this service is part of if one is running
            await self.force_stop_experiment(exc_obj.uuid)
        else:
            raise ExceptionUnhandledError

    @logfire.instrument("Start Experiment")
    async def start_experiment(self, experiment: ExperimentDescriptor) -> None:
        """Logic for starting an experiment."""
        self.connected_services[experiment.room_uuid].in_experiment = True
        self.connected_services[experiment.game_uuid].in_experiment = True
        self.connected_services[experiment.defuser_uuid].in_experiment = True
        if experiment.expert_uuid:
            self.connected_services[experiment.expert_uuid].in_experiment = True

        logger.info(f"Starting experiment: {experiment}")
        await self.api_queues.room_command(experiment.room_uuid).route.publish(
            StartExperimentCommand(experiment_descriptor=experiment)
        )

    async def force_stop_experiment(self, service_uuid: UUID4) -> None:
        """Forces the experiment containing the passed service to stop."""
        with suppress(KeyError):
            experiment = {
                experiment
                for experiment in self.running_experiments
                if service_uuid in experiment.service_uuids
            }.pop()

            logger.warning(f"Stopping experiment: {experiment}")
            self.running_experiments.remove(experiment)

            # If the room fails to stop the subservices, stop them manually
            if not await self.api_queues.room_command(experiment.room_uuid).route.publish_with_ack(
                StopExperimentCommand(hard_crash=True), fail_after=15
            ):
                await remove_experiment_bindings(experiment=experiment, api_queues=self.api_queues)
                await self.api_queues.game_command(experiment.game_uuid).route.publish(
                    StopExperimentCommand(hard_crash=True)
                )
                await self.api_queues.player_command(experiment.defuser_uuid).route.publish(
                    StopExperimentCommand(hard_crash=True)
                )
                if experiment.expert_uuid:
                    await self.api_queues.player_command(experiment.expert_uuid).route.publish(
                        StopExperimentCommand(hard_crash=True)
                    )

    async def handle_connection(self, connect_event: ConnectEvent) -> None:
        """Handles a command from the Experiment Manager."""
        logger.info(f"Service connected: {connect_event}")

        # Register the new service and start its watchdog
        if isinstance(connect_event, PlayerConnectEvent):
            service = ConnectedPlayerService(
                connect_event=connect_event,
                player_metadata=connect_event.metadata,
                watchdog=HeartbeatWatchdog(
                    fail_after=30.0,
                    fail_exception=HeartbeatWatchdogTriggeredError(
                        uuid=connect_event.uuid, metadata=connect_event.metadata.model_dump()
                    ),
                ),
            )
        else:
            service = ConnectedService(
                connect_event=connect_event,
                watchdog=HeartbeatWatchdog(
                    fail_after=30.0,
                    fail_exception=HeartbeatWatchdogTriggeredError(
                        uuid=connect_event.uuid, metadata={"type": connect_event.event}
                    ),
                ),
            )

        self.connected_services[connect_event.uuid] = service
        _ = self.background_tasks.create_task(service.watchdog.watchdog_loop())

    async def handle_ready(self, ready_event: ReadinessEvent) -> None:
        """Handles a readiness event received from a service."""
        try:
            service = self.connected_services[ready_event.uuid]
        except KeyError:
            logger.warning(f"Received ready event from unknown service: {ready_event}")
            return

        logger.info(f"Received ready event: {ready_event}")

        if isinstance(ready_event, ReadyEvent):
            service.is_ready = True
            service.in_experiment = False

        if isinstance(ready_event, NotReadyEvent):
            service.is_ready = False

            if service.in_experiment:
                await self.force_stop_experiment(service_uuid=ready_event.uuid)

    async def handle_heartbeat(self, heartbeat: HeartbeatEvent) -> None:
        """Handles an incomming heartbeat."""
        with suppress(KeyError):
            self.connected_services[heartbeat.uuid].watchdog_flag.set()

    async def handle_new_spec(self, spec: list[ExperimentSpec]) -> None:
        """Handles receiving a new experiment spec."""
        self.specs.update(set(spec))
        logger.info(f"Total specs: {len(self.specs)}")

    async def handle_experiment_done(self, event: ExperimentDoneEvent) -> None:
        """Handles ExperimentDoneEvent events."""
        logger.info(f"Received done event: {event}")

        with suppress(KeyError):
            self.running_experiments.remove(event.experiment_descriptor)

    async def matchmaking_loop(self) -> None:  # noqa: WPS231
        """Performs matchmaking."""
        while True:  # noqa: WPS457
            self._update_logfire_gauges()
            playable_pairings = get_playable_pairings(
                available_players=self.ready_players, available_experiments=list(self.specs)
            )
            for pairing in playable_pairings:
                if not (rooms := self.ready_rooms) or not (games := self.ready_games):
                    # No rooms or games available, can't start any more pairings
                    continue

                # Get the room and a game
                room = rooms.pop()
                game = games.pop()
                # Remove the experiment spec from the pool
                self.specs.remove(pairing.experiment)
                # throw the experiment
                next_experiment = ExperimentDescriptor(
                    room_uuid=room.uuid,
                    game_uuid=game.uuid,
                    defuser_uuid=pairing.defuser.uuid,
                    expert_uuid=pairing.expert.uuid if pairing.expert else None,
                    experiment_spec=pairing.experiment,
                )
                await self.start_experiment(experiment=next_experiment)  # noqa: WPS476
                self.running_experiments.add(next_experiment)

            await busy_wait_interval()

    @overload
    def _filter_ready_services_by_type(
        self, connection_type: type[PlayerConnectEvent]
    ) -> list[ConnectedPlayerService]: ...

    @overload
    def _filter_ready_services_by_type(
        self, connection_type: type[GameConnectEvent] | type[RoomConnectEvent]
    ) -> list[ConnectedService]: ...

    def _filter_ready_services_by_type(
        self, connection_type: type[ConnectEvent]
    ) -> list[ConnectedService] | list[ConnectedPlayerService]:
        """List of all connected and ready services with the passed ConnectEvent type."""
        return [
            service
            for service in self.connected_services.values()
            if service.is_ready
            and not service.in_experiment
            and isinstance(service.connect_event, connection_type)
        ]

    def _update_logfire_gauges(self) -> None:
        """Update the Logfire gauges with the current counts."""
        rooms = [
            service
            for service in self.connected_services.values()
            if isinstance(service.connect_event, RoomConnectEvent) and service.is_ready
        ]
        games = [
            service
            for service in self.connected_services.values()
            if isinstance(service.connect_event, GameConnectEvent) and service.is_ready
        ]
        players = [
            service
            for service in self.connected_services.values()
            if isinstance(service.connect_event, PlayerConnectEvent) and service.is_ready
        ]

        LogfireGauge.connected_rooms.set(len(rooms))
        LogfireGauge.connected_players.set(len(players))
        LogfireGauge.connected_games.set(len(games))

        LogfireGauge.available_experiments.set(len(self.specs))
        LogfireGauge.running_experiments.set(len(self.running_experiments))

        LogfireGauge.running_rooms.set(len([room for room in rooms if room.in_experiment]))
        LogfireGauge.running_players.set(
            len([player for player in players if player.in_experiment])
        )
        LogfireGauge.running_games.set(len([game for game in games if game.in_experiment]))
