import abc
from contextlib import suppress
from dataclasses import InitVar, dataclass, field
from typing import Self, override

import httpx
import logfire
from structlog import get_logger

from gptnt.common.instrumentation import InstrumentationDataclassMixin

_logger = get_logger()


TimeoutTypes = float | httpx.Timeout | None

DEFAULT_CONNECTION_LIMITS = httpx.Limits(
    max_connections=10, max_keepalive_connections=5, keepalive_expiry=30.0
)
# default timeout is 10 minutes
DEFAULT_TIMEOUT = httpx.Timeout(timeout=10 * 60, connect=5.0, pool=60.0)


def httpx_create_async_client(base_url: str | httpx.URL) -> httpx.AsyncClient:
    """Make shared client instance with httpx_aiohttp."""
    return httpx.AsyncClient(
        limits=DEFAULT_CONNECTION_LIMITS, timeout=DEFAULT_TIMEOUT, base_url=base_url
    )


@dataclass(kw_only=True)
class BaseClient(InstrumentationDataclassMixin, abc.ABC):
    """Base class for all clients."""

    url: InitVar[str | httpx.URL] = ""
    _client: httpx.AsyncClient = field(init=False)

    def __post_init__(self, url: str | httpx.URL) -> None:
        """Post-initialization method to create the HTTP client."""
        self._client = httpx_create_async_client(base_url=url)

    @property
    def base_url(self) -> httpx.URL:
        """The base URL of the API."""
        return self._client.base_url

    @property
    def client(self) -> httpx.AsyncClient:
        """The HTTP client."""
        if self._client.is_closed:
            self.recreate_client()
        return self._client

    def recreate_client(self, *, url: str | httpx.URL | None = None) -> None:
        """Create a new httpx client."""
        url = url or self.base_url
        self._client = httpx_create_async_client(base_url=url)
        self.perform_instrumentation()

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
        logfire.instrument_httpx(
            self.client,
            capture_headers=True,
            capture_request_body=True,
            capture_response_body=False,
        )

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
                    "Healthcheck failed", class_name=self.__class__.__name__, url=self.base_url
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

    def clear_client_url(self) -> None:
        """Reset the client url.

        Basically we do this to prevent any accidental messages being send to the wrong URL.
        """
        self.recreate_client(url="")
