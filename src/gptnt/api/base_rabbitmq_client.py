import asyncio
import sys
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from types import TracebackType

from aiotools import PersistentTaskGroup
from faststream.rabbit import RabbitBroker

from gptnt.api.api import APIQueues, APIRoutes
from gptnt.api.exceptions import ExceptionUnhandledError


@dataclass(kw_only=True)
class BaseRabbitMQClient(ABC):
    """Base RabbitMQ client.

    Provides lifespan and asyncio management utilities.
    """

    broker: RabbitBroker
    api_queues: APIQueues = field(init=False)
    api_routes: APIRoutes = field(init=False)

    background_tasks: PersistentTaskGroup = field(init=False)

    def __post_init__(self) -> None:
        """Initialises the basic RabbitMQ functionality BEFORE app startup."""
        self.api_queues = APIQueues(broker=self.broker)
        self.api_routes = APIRoutes(broker=self.broker)

    @abstractmethod
    async def handle_background_task_exception(
        self,
        exc_type: type[BaseException] | None = None,
        exc_obj: BaseException | None = None,
        exc_tb: TracebackType | None = None,
    ) -> None:
        """What to do when a background task raises an exception."""
        raise NotImplementedError("No background task exception handler override provided.")

    @abstractmethod
    async def lifespan_setup(self) -> None:
        """Setup logic for the client, runs on app start."""
        raise NotImplementedError(
            "BaseRabbitMQClient does not have a lifespan, please override `lifespan_setup` and `lifespan_cleanup` in child."
        )

    @abstractmethod
    async def lifespan_cleanup(self) -> None:
        """Cleanup logic for the client, runs after app is closed."""
        raise NotImplementedError(
            "BaseRabbitMQClient does not have a lifespan, please override `lifespan_setup` and `lifespan_cleanup` in child."
        )

    @asynccontextmanager
    async def lifespan(self) -> AsyncGenerator[None]:
        """Lifespan for the client.

        Performs the startup logic for the client, yields, then performs cleanup after returning to
        the yield.
        """
        self.background_tasks = await PersistentTaskGroup(
            name="background_tasks",
            exception_handler=self._background_task_exception_handler_wrapper,
        ).__aenter__()
        await self.lifespan_setup()
        yield
        await self.lifespan_cleanup()
        await self.background_tasks.shutdown()

    async def shutdown(self, *, exit_message: str = "No shutdown reason provided") -> None:
        """Gracefully closes the running service, and kills the underlying python process."""
        with suppress(TimeoutError):
            async with asyncio.timeout(delay=5.0):
                await self.lifespan_cleanup()

        sys.exit(exit_message)

    async def _background_task_exception_handler_wrapper(
        self,
        exc_type: type[BaseException] | None = None,
        exc_obj: BaseException | None = None,
        exc_tb: TracebackType | None = None,
    ) -> None:
        """Pass the exception to the child class to handle.

        If the child class does not handle the exception then fall over.
        """
        try:
            await self.handle_background_task_exception(exc_type, exc_obj, exc_tb)
        except ExceptionUnhandledError:
            # TODO: May be good to remove this for production
            await self.shutdown(
                exit_message=f"Uncaught exception [{exc_type}] in background task:\n{exc_tb}"
            )
