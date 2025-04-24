import abc
from contextlib import suppress
from typing import Self, override

import httpx
import logfire
from structlog import get_logger

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
        """Checks the health of the client."""
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
