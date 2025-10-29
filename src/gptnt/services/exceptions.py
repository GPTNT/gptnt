from collections.abc import Awaitable, Callable
from types import MappingProxyType
from typing import Any

import httpx
import structlog
from fastapi import HTTPException
from faststream import ExceptionMiddleware
from faststream.redis import RedisMessage

logger = structlog.get_logger()


# Exception registry for serialization/deserialization across RPC boundaries to maps exception
# type names (strings) to their Python classes
# Note: We convert FastAPI's HTTPException to httpx.HTTPStatusError in the decoder so clients can
# use standard httpx exception catching patterns (since that's what the codebase was made with)
EXCEPTION_REGISTRY: MappingProxyType[str, type[Exception]] = MappingProxyType(
    {
        "HTTPStatusError": httpx.HTTPStatusError,
        "TimeoutException": httpx.TimeoutException,
        "RequestError": httpx.RequestError,
    }
)

exc_middleware = ExceptionMiddleware()


@exc_middleware.add_handler(httpx.HTTPStatusError, publish=True)
def handle_http_error(exc: httpx.HTTPStatusError) -> dict[str, Any]:
    """Serialize httpx.HTTPStatusError for transmission over RPC.

    Returns dict with __exception__ marker so client can reconstruct and raise it.
    """
    return {
        "__exception__": True,
        "type": "HTTPStatusError",
        "message": str(exc),
        "status_code": exc.response.status_code,
        "response_text": exc.response.text,
        "request_url": str(exc.request.url),
    }


@exc_middleware.add_handler(HTTPException, publish=True)
def handle_http_exception(exc: HTTPException) -> dict[str, Any]:
    """Convert FastAPI HTTPException to httpx.HTTPStatusError format for RPC.

    This allows clients to catch exceptions using standard httpx patterns instead of importing
    FastAPI's HTTPException. The conversion is transparent to both server (raises HTTPException)
    and client (catches httpx.HTTPStatusError).

    Returns dict with __exception__ marker so client can reconstruct and raise it.
    """
    # Build response text with detail and optional headers
    response_text = str(exc.detail)
    if exc.headers:
        headers_info = ", ".join(f"{name}: {header}" for name, header in exc.headers.items())
        response_text = f"{response_text} (headers: {headers_info})"

    return {
        "__exception__": True,
        # Convert to httpx type
        "type": "HTTPStatusError",
        "message": str(exc.detail),
        "status_code": exc.status_code,
        "response_text": response_text,
        "request_url": "http://service/rpc",
        "headers": dict(exc.headers) if exc.headers else None,
    }


@exc_middleware.add_handler(httpx.TimeoutException, publish=True)
def handle_timeout(exc: httpx.TimeoutException) -> dict[str, Any]:
    """Serialize httpx.TimeoutException for transmission over RPC.

    Returns dict with __exception__ marker so client can reconstruct and raise it.
    """
    return {"__exception__": True, "type": "TimeoutException", "message": str(exc)}


@exc_middleware.add_handler(httpx.RequestError, publish=True)
def handle_request_error(exc: httpx.RequestError) -> dict[str, Any]:
    """Serialize httpx.RequestError for transmission over RPC.

    Returns dict with __exception__ marker so client can reconstruct and raise it.
    """
    return {
        "__exception__": True,
        "type": "RequestError",
        "message": str(exc),
        "request_url": str(exc.request.url) if exc.request else None,
    }


def decode_http_status_error(data: dict[str, Any]) -> None:
    """Reconstruct and raise httpx.HTTPStatusError from serialized data."""
    # Reconstruct httpx.HTTPStatusError with minimal request/response
    request = httpx.Request("POST", data.get("request_url", "http://service/rpc"))

    # Build response with headers if they were provided (from FastAPI HTTPException)
    headers_data = data.get("headers")
    response_headers = list(headers_data.items()) if headers_data else []

    response = httpx.Response(
        status_code=data.get("status_code", 500),
        request=request,
        text=data.get("response_text", ""),
        headers=response_headers,
    )
    raise httpx.HTTPStatusError(
        data.get("message", "HTTP error"), request=request, response=response
    )


def decode_timeout_error(data: dict[str, Any]) -> None:
    """Reconstruct and raise httpx.TimeoutException from serialized data."""
    raise httpx.TimeoutException(data.get("message", "Request timed out"))


def decode_request_error(data: dict[str, Any]) -> None:
    """Reconstruct and raise httpx.RequestError from serialized data."""
    request = httpx.Request("POST", data.get("request_url", "http://service/rpc"))
    raise httpx.RequestError(data.get("message", "Request error"), request=request)


async def exception_aware_decoder(
    msg: RedisMessage, original_decoder: Callable[[RedisMessage], Awaitable[Any]]
) -> Any:
    """Decode RPC responses and raise exceptions if marked as such.

    This decoder wraps the original FastStream decoder and checks if the decoded message is an
    exception payload. If so, it reconstructs the exception and raises it, making RPC exceptions
    behave like HTTP exceptions.
    """
    # Decode the message normally first
    data = await original_decoder(msg)

    # Check if this is an exception payload
    if not isinstance(data, dict) or not data.get("__exception__"):
        return data

    # Extract exception info
    exc_type_name = data.get("type", "")
    exc_class = EXCEPTION_REGISTRY.get(exc_type_name)
    logger.debug("Reconstructing remote exception", exc_type=exc_type_name, data=data)

    if not exc_class:
        # Unknown exception type - raise generic error
        raise RuntimeError(
            f"Remote exception ({exc_type_name}): {data.get('message', 'Unknown error')}"
        )

    match exc_type_name:
        case "HTTPStatusError":
            return decode_http_status_error(data)
        case "TimeoutException":
            return decode_timeout_error(data)
        case "RequestError":
            return decode_request_error(data)
        case _:
            # Fallback for any other registered exception types
            raise exc_class(data.get("message", "Unknown error"))
