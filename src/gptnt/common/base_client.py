import abc
from contextlib import suppress
from typing import Self, override

import httpx
import logfire
from structlog import get_logger

from gptnt.common.instrumentation import InstrumentationMixin
from gptnt.common.servers import ClientMetadata, httpx_create_async_client

_logger = get_logger()


class BaseClient(InstrumentationMixin, abc.ABC):
    """Base class for all clients."""

    def __init__(self, url: str | httpx.URL) -> None:
        self._client = httpx_create_async_client(base_url=url)

    @property
    def url(self) -> httpx.URL:
        """The base URL of the API."""
        return self.client.base_url

    @property
    def client(self) -> httpx.AsyncClient:
        """The HTTP client."""
        if self._client.is_closed:
            _logger.debug("Creating new httpx client")
            self._client = httpx_create_async_client(base_url=self.url)
            self.perform_instrumentation()
        return self._client

    @property
    def is_closed(self) -> bool:
        """Returns true if the client is closed."""
        return self.client.is_closed

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

    def __init__(self, client: ClientT, metadata: MetadataT) -> None:
        self.is_running = False
        self.in_experiment = False
        self.metadata = metadata
        self.client = client

    @classmethod
    def from_metadata(cls, metadata: MetadataT) -> Self:
        """Creates a new client from the metadata."""
        if not metadata.fastapi_url:
            raise ValueError("URL is required")
        return cls(client=cls.client_constructor(metadata.fastapi_url), metadata=metadata)

    @property
    def url(self) -> httpx.URL:
        """The base URL of the API."""
        return self.client.url

    @property
    def is_closed(self) -> bool:
        """Returns true if the client is closed."""
        return self.client.is_closed

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
