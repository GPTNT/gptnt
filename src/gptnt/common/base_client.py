from contextlib import suppress
from dataclasses import InitVar, dataclass, field
from functools import cache
from typing import Self

import httpx
from pydantic_ai.models import get_user_agent
from pydantic_ai.retries import AsyncTenacityTransport, RetryConfig, wait_retry_after
from structlog import get_logger
from tenacity import (
    RetryCallState,
    retry_if_exception_type,
    stop_after_attempt,
    stop_after_delay,
    wait_exponential,
)

_logger = get_logger()


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
class ManagedHttpClient:
    """Managed async HTTP client with lifecycle and health checks."""

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


MAX_RETRYING_CLIENT_WAIT_SECONDS = 180
MAX_RETRYING_CLIENT_ATTEMPTS = 5
MAX_CLIENT_TIMEOUT_SECONDS = 120
RETRYABLE_HTTP_CODES = frozenset((429, 502, 503, 504, 524))


def cached_retrying_async_http_client(
    *, provider: str | None = None, timeout: int = MAX_CLIENT_TIMEOUT_SECONDS, connect: int = 5
) -> httpx.AsyncClient:
    """Cached retrying HTTPX async client that creates a separate client for each provider.

    We copy-paste and extend the logic from Pydantic AI's cached_async_http_client to add the
    retrying transport while still handling the closed client gracefully.
    """
    client = _cached_retrying_async_http_client(
        provider=provider, timeout=timeout, connect=connect
    )
    if client.is_closed:
        # This happens if the context manager is used, so we need to create a new client.
        # Since there is no API from `functools.cache` to clear the cache for a specific
        #  key, clear the entire cache here as a workaround.
        _cached_retrying_async_http_client.cache_clear()
        client = _cached_retrying_async_http_client(
            provider=provider, timeout=timeout, connect=connect
        )
    return client


@cache
def _cached_retrying_async_http_client(
    provider: str | None,  # noqa: ARG001
    timeout: int = MAX_CLIENT_TIMEOUT_SECONDS,
    connect: int = 5,
) -> httpx.AsyncClient:
    """Create a cached async http client that also has the retrying transport.

    This is an extended version of the _cached_async_http_client from Pydantic AI so we can add and
    cache the transport to deal with possible closed clients easily.

    Impl for transport is from: https://ai.pydantic.dev/retries/#usage-example
    """
    transport = AsyncTenacityTransport(
        config=RetryConfig(
            # Retry on HTTP errors and connection issues
            retry=retry_if_exception_type((httpx.HTTPStatusError, ConnectionError)),
            # Smart waiting: respects Retry-After headers, falls back to exponential backoff
            wait=wait_retry_after(
                fallback_strategy=wait_exponential(multiplier=1, max=60), max_wait=60
            ),
            # Stop after <num> attempts or a maximum wall clock time, whichever comes first
            stop=stop_after_attempt(MAX_RETRYING_CLIENT_ATTEMPTS)
            | stop_after_delay(MAX_RETRYING_CLIENT_WAIT_SECONDS),
            # When the retrying gives up, it will raise tenacity.RetryError
            reraise=False,
            before_sleep=_log_retry,
        ),
        validate_response=_should_retry_status,
    )
    return httpx.AsyncClient(
        timeout=httpx.Timeout(timeout=timeout, connect=connect),
        headers={"User-Agent": get_user_agent()},
        transport=transport,
    )


def _should_retry_status(response: httpx.Response) -> None:
    """Raise exceptions for retryable HTTP status codes."""
    if response.status_code in RETRYABLE_HTTP_CODES:
        _ = response.raise_for_status()


def _log_retry(retry_state: RetryCallState) -> None:
    """Log retry attempts."""
    _logger.warning(
        "HTTP request failed, retrying...",
        attempt=retry_state.attempt_number,
        next_wait=retry_state.next_action.sleep if retry_state.next_action else None,
        exception=str(retry_state.outcome.exception()) if retry_state.outcome else None,
        seconds_since_start=retry_state.seconds_since_start,
    )
