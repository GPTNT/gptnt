from collections.abc import Generator
from typing import Any, override

import httpx
import pytest
from pydantic_ai.retries import AsyncTenacityTransport, RetryConfig
from tenacity import retry_if_exception_type, stop_after_attempt, wait_none

from gptnt.core.common.base_client import (
    MAX_RETRYING_CLIENT_ATTEMPTS,
    _cached_retrying_async_http_client,
    _should_retry_status,
    cached_retrying_async_http_client,
)


@pytest.mark.parametrize(
    ("status_code", "should_raise"),
    [
        (429, True),
        (502, True),
        (503, True),
        (504, True),
        (200, False),
        (201, False),
        (404, False),
        (500, False),
    ],
)
def test_should_retry_status(status_code: int, should_raise: bool) -> None:
    """Only the four retryable status codes should raise HTTPStatusError."""
    response = httpx.Response(status_code=status_code, request=httpx.Request("GET", "http://test"))
    if should_raise:
        with pytest.raises(httpx.HTTPStatusError):
            _should_retry_status(response)
    else:
        _should_retry_status(response)  # must not raise


class _QueuedMockTransport(httpx.AsyncBaseTransport):
    """Returns pre-configured responses in FIFO order and counts calls."""

    def __init__(self, responses: list[httpx.Response]) -> None:
        self._responses = list(responses)
        self.call_count = 0

    @override
    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.call_count += 1
        response = self._responses.pop(0)
        # httpx normally sets this after the transport returns; do it here so
        # raise_for_status() inside validate_response has a valid request.
        response.request = request
        return response


def _build_transport(
    responses: list[httpx.Response],
) -> tuple[AsyncTenacityTransport, _QueuedMockTransport]:
    """Build an AsyncTenacityTransport wrapping a queued mock with no wait delays."""
    mock = _QueuedMockTransport(responses)
    transport = AsyncTenacityTransport(
        config=RetryConfig(
            retry=retry_if_exception_type((httpx.HTTPStatusError, ConnectionError)),
            wait=wait_none(),  # skip real delays in tests
            stop=stop_after_attempt(MAX_RETRYING_CLIENT_ATTEMPTS),
            reraise=True,
        ),
        wrapped=mock,
        validate_response=_should_retry_status,
    )
    return transport, mock


@pytest.mark.anyio
async def test_retrying_transport_no_retry_on_success() -> None:
    """A 200 response requires exactly one attempt."""
    transport, mock = _build_transport([httpx.Response(200)])

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")

    assert response.status_code == 200
    assert mock.call_count == 1


@pytest.mark.anyio
async def test_retrying_transport_succeeds_after_retries() -> None:
    """Transport should succeed when retryable responses precede a 200."""
    transport, mock = _build_transport(
        [httpx.Response(429), httpx.Response(429), httpx.Response(200)]
    )

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")

    assert response.status_code == 200
    assert mock.call_count == 3


@pytest.mark.anyio
async def test_retrying_transport_exhaust_raises() -> None:
    """After MAX_RETRYING_CLIENT_ATTEMPTS retryable responses the transport re-raises."""
    transport, mock = _build_transport(
        [httpx.Response(429) for _ in range(MAX_RETRYING_CLIENT_ATTEMPTS)]
    )

    with pytest.raises(httpx.HTTPStatusError):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            _ = await client.get("/")

    assert mock.call_count == MAX_RETRYING_CLIENT_ATTEMPTS


@pytest.mark.parametrize("status_code", [502, 503, 504])
@pytest.mark.anyio
async def test_retrying_transport_retries_all_retryable_codes(status_code: int) -> None:
    """All four retryable status codes trigger a retry, not just 429."""
    transport, mock = _build_transport([httpx.Response(status_code), httpx.Response(200)])

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")

    assert response.status_code == 200
    assert mock.call_count == 2


@pytest.fixture(autouse=True)
def clear_client_cache() -> Generator[Any]:
    """Ensure a clean cache before and after every test in this module."""
    _cached_retrying_async_http_client.cache_clear()
    yield
    _cached_retrying_async_http_client.cache_clear()


def test_cached_client_same_provider_returns_same_instance() -> None:
    """Calling with the same provider twice must return the identical object."""
    one = cached_retrying_async_http_client(provider="acme")
    two = cached_retrying_async_http_client(provider="acme")
    assert one is two


def test_cached_client_different_providers_return_different_instances() -> None:
    """Different provider keys must produce independent clients."""
    one = cached_retrying_async_http_client(provider="alpha")
    two = cached_retrying_async_http_client(provider="beta")
    assert one is not two


@pytest.mark.anyio
async def test_cached_client_refreshes_closed_client() -> None:
    """If the cached client has been closed a fresh open client is returned."""
    stale = cached_retrying_async_http_client(provider="closed-provider")
    await stale.aclose()

    fresh = cached_retrying_async_http_client(provider="closed-provider")

    assert not fresh.is_closed
    assert fresh is not stale
