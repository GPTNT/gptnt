import abc
from contextlib import suppress
from typing import Self, override

import httpx
import logfire
from structlog import get_logger

from gptnt.api.structures import ClientMetadata
from gptnt.common.instrumentation import InstrumentationMixin

_logger = get_logger()


class BaseClient(InstrumentationMixin, abc.ABC):
    """Base class for all clients."""

    def __init__(self, url: str | httpx.URL) -> None:
        self.client = httpx.AsyncClient(base_url=url)

    @property
    def url(self) -> httpx.URL:
        """The base URL of the API."""
        return self.client.base_url

    async def start(self) -> Self:
        """Opens the API."""
        _ = await self.client.__aenter__()
        return self

    async def stop(self) -> None:
        """Closes the API."""
        _ = await self.client.__aexit__()

    @override
    def perform_instrumentation(self) -> None:
        _logger.debug(f"Instrumenting {self.__class__.__name__}")
        logfire.instrument_httpx(self.client, capture_all=True)

    async def healthcheck(self, *, skip_logger: bool = False) -> bool:
        """Checks the health of the client.

        Optional skip_logger argument to skip logging if the healthcheck fails, which is useful to
        prevent spamming the logs during startup.
        """
        try:
            _ = (await self.client.get(url="/health")).raise_for_status()
        except httpx.HTTPError:
            if not skip_logger:
                _logger.warning(
                    "Healthcheck failed", class_name=self.__class__.__name__, url=self.url
                )
            return False
        return True

    async def wait_for_valid_healthcheck(self) -> bool:
        """Wait for a valid healthcheck.

        Returns true if the RoomManager is healthy, else false.
        """
        _logger.debug("Waiting for valid healthcheck")
        with suppress(httpx.HTTPError, TimeoutError):
            if await self.healthcheck(skip_logger=True):
                return True

        return False


class SupervisedClient[ClientT: BaseClient, MetadataT: ClientMetadata](abc.ABC):
    """Wrapper to supervise clients."""

    client_constructor: type[ClientT]
    supervisor_interval: float = 0.5

    def __init__(self, client: ClientT, metadata: MetadataT) -> None:
        self.is_running = False
        self.in_experiment = False
        self.metadata = metadata
        self.client = client

    @classmethod
    def from_metadata(cls, metadata: MetadataT) -> Self:
        """Creates a new client from the metadata."""
        return cls(client=cls.client_constructor(metadata.fastapi_url), metadata=metadata)

    async def start(self) -> None:
        """Starts the client."""
        self.is_running = True
        _ = await self.client.start()

    async def stop(self) -> None:
        """Stops the client."""
        self.is_running = False
        _ = await self.client.stop()

    @abc.abstractmethod
    async def supervisor_loop(self) -> None:
        """Returns the supervisor loop for this client."""
        raise NotImplementedError
