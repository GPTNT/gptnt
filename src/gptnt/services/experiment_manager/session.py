from dataclasses import dataclass, field
from typing import override
from uuid import uuid4

import anyio
import structlog
from anyio.abc import TaskGroup
from coredis import Redis
from faststream.redis import RedisBroker
from pydantic import UUID4

from gptnt.experiments.experiment_descriptor import ExperimentDescriptor
from gptnt.experiments.experiments import ExperimentSpec
from gptnt.services.experiment_manager.experiment_runner import (
    AsyncExperimentRunner,
    ExperimentRunner,
    ExperimentState,
    SyncExperimentRunner,
)
from gptnt.services.registry.manifest import (
    GameServiceManifest,
    PlayerServiceManifest,
    ServiceState,
)

logger = structlog.get_logger()


@dataclass(kw_only=True)
class Session:
    """Create a session instance to manage a running experiment."""

    game: GameServiceManifest
    defuser: PlayerServiceManifest
    expert: PlayerServiceManifest | None = None

    spec: ExperimentSpec

    redis: Redis[str]
    redis_broker: RedisBroker

    experiment_uuid: UUID4 = field(default_factory=uuid4, init=False)

    experiment_runner: ExperimentRunner = field(init=False)
    _cancel_scope: anyio.CancelScope = field(
        default_factory=anyio.CancelScope, init=False, repr=False
    )
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
        return f"{self.spec.attempt_name}--{self.experiment_uuid}"

    @property
    def state(self) -> ExperimentState:
        """Get the current state of the room instance."""
        return self.experiment_runner.state

    @property
    def is_hard_crash(self) -> bool:
        """Check if the experiment is in a crashed state."""
        return self.experiment_runner.is_hard_crash

    @property
    def is_stopping(self) -> bool:
        """Check if the experiment is in the process of stopping."""
        return self.state > ExperimentState.running

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

    async def run(self) -> None:
        """Run the experiment. Blocks until done or cancelled.

        Must be spawned in its own task (e.g. via ``tg.start_soon``) so the cancel scope lives in
        that task, **not** in the caller's. ``force_stop_experiment`` can then safely cancel the
        scope without affecting sibling tasks.
        """
        logger.info("Session starting", experiment=self.name, spec=self.spec)
        with self._cancel_scope:
            async with anyio.create_task_group() as tg:
                self._task_group = tg
                tg.start_soon(self.experiment_runner.run_experiment)

    async def force_stop_experiment(self) -> None:
        """Stop the current experiment."""
        if self.is_stopping:
            logger.debug(
                "Experiment is already being stopped, not doing anything", experiment=self.name
            )
            return

        self.defuser.state = ServiceState.cleanup
        self.game.state = ServiceState.cleanup
        if self.expert:
            self.expert.state = ServiceState.cleanup
        self.experiment_runner.state = ExperimentState.cleanup

        logger.info("Setting `client_crashed_event`", experiment=self.name)
        self.experiment_runner.client_crashed_event.set()

        # Force-cancel the session's scope to interrupt any blocked awaits (e.g. an RPC to a dead
        # service).  Because run() is in its own task, this only affects the session — not the EM
        # or matchmaking loop.
        logger.info("Cancelling experiment scope", experiment=self.name)
        self._cancel_scope.cancel()

        logger.info("Session stopped", experiment=self.name)

    async def cleanup(self) -> None:
        """Clean up the session so it can be deleted."""
        self._task_group = None

        self.defuser.state = ServiceState.idle
        if self.expert:
            self.expert.state = ServiceState.idle
        self.game.state = ServiceState.idle

        logger.info("Session cleaned up", experiment=self.name)

    def _create_runner(self) -> ExperimentRunner:
        """Create an experiment runner based on the communication style."""
        match self.spec.communication_style:
            case "sync":
                return SyncExperimentRunner(
                    experiment=self.experiment_descriptor,
                    redis=self.redis,
                    redis_broker=self.redis_broker,
                )
            case "async":
                return AsyncExperimentRunner(
                    experiment=self.experiment_descriptor,
                    redis=self.redis,
                    redis_broker=self.redis_broker,
                )
