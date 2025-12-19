import atexit
from dataclasses import dataclass, field
from typing import override
from uuid import uuid4

import anyio
import structlog
from anyio.abc import TaskGroup
from pydantic import UUID4, RedisDsn

from gptnt.experiments.experiments import ExperimentSpec
from gptnt.services.experiment_descriptor import ExperimentDescriptor
from gptnt.services.registry.manifest import (
    GameServiceManifest,
    PlayerServiceManifest,
    ServiceState,
)
from gptnt.services.sessions.experiment_runner import (
    # AsyncExperimentRunner,
    ExperimentRunner,
    ExperimentState,
    SyncExperimentRunner,
)

logger = structlog.get_logger()


@dataclass(kw_only=True)
class Session:
    """Create a session instance to manage a running experiment."""

    game: GameServiceManifest
    defuser: PlayerServiceManifest
    expert: PlayerServiceManifest | None = None

    spec: ExperimentSpec

    redis_url: RedisDsn = field(default=RedisDsn("redis://localhost:6379"))

    experiment_uuid: UUID4 = field(default_factory=uuid4, init=False)

    experiment_runner: ExperimentRunner = field(init=False)
    _task_group: TaskGroup | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        """Initialise the room instance."""
        self.experiment_runner = self._create_runner()

    @override
    def __hash__(self) -> int:
        return hash((*self.service_uuids, self.experiment_uuid, hash(self.spec)))

    @property
    def name(self) -> str:
        """Get the name of the room instance, which is just the experiment name."""
        return f"{self.spec.experiment_name}--{self.experiment_uuid}"

    @property
    def state(self) -> ExperimentState:
        """Get the current state of the room instance."""
        return self.experiment_runner.state

    @property
    def is_hard_crash(self) -> bool:
        """Check if the experiment is in a crashed state."""
        return self.experiment_runner.is_hard_crash

    @property
    def experiment_descriptor(self) -> ExperimentDescriptor:
        """Get the experiment descriptor for this room instance."""
        return ExperimentDescriptor(
            experiment_spec=self.spec,
            session_id=self.experiment_uuid,
            expert_uuid=self.expert.uuid if self.expert else None,
            defuser_uuid=self.defuser.uuid,
            game_uuid=self.game.uuid,
        )

    @property
    def service_uuids(self) -> list[UUID4]:
        """List of UUIDs for the services in this experiment."""
        services = [self.defuser.uuid, self.game.uuid]
        if self.expert:
            services.append(self.expert.uuid)
        return services

    @property
    def has_exceptions(self) -> bool:
        """Check if the task group for running it has exceptions."""
        return self._task_group is not None and getattr(self._task_group, "_exceptions", False)

    async def start_experiment(self) -> None:
        """Start the current experiment."""
        self._task_group = await anyio.create_task_group().__aenter__()
        self._task_group.start_soon(self.experiment_runner.run_experiment)
        # If it's not done already, by the time we exit the app, ensure the task group is
        # cancelled and cleaned up
        _ = atexit.register(self._task_group.cancel_scope.cancel)

    async def stop_experiment(self) -> None:
        """Stop the current experiment."""
        if self._task_group is None:
            logger.error("Run experiment task group is not initialised")
            return

        self.defuser.state = ServiceState.cleanup
        self.game.state = ServiceState.cleanup
        if self.expert:
            self.expert.state = ServiceState.cleanup
        self.experiment_runner.state = ExperimentState.cleanup

        logger.info("Setting `client_crashed_event`", experiment=self.name)
        self.experiment_runner.client_crashed_event.set()
        # Wait a bit to ensure things have a chance to stop gracefully
        logger.info("Session stopped", experiment=self.name)

    async def cleanup(self) -> None:
        """Clean up the session so it can be deleted."""
        if self._task_group is not None:
            _ = atexit.unregister(self._task_group.cancel_scope.cancel)
        self._task_group = None

        self.defuser.state = ServiceState.idle
        if self.expert:
            self.expert.state = ServiceState.idle
        self.game.state = ServiceState.idle

        logger.info("Session cleaned up", experiment=self.name)

    def _create_runner(self) -> SyncExperimentRunner:
        """Create an experiment runner based on the communication style."""
        match self.spec.communication_style:
            case "sync":
                logger.debug("Creating sync experiment runner")
                return SyncExperimentRunner(
                    experiment=self.experiment_descriptor, redis_url=self.redis_url
                )
            case "async":
                logger.debug("Creating async experiment runner")
                raise NotImplementedError
                # return AsyncExperimentRunner(
                #     experiment=self.experiment_descriptor, redis_url=self.redis_url
                # )
