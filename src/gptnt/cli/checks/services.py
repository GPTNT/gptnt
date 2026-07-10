"""`gptnt doctor` service-reachability checks: Redis, the EM port, and the OTLP collector."""

from __future__ import annotations

from urllib.parse import urlsplit

import anyio
import httpx

from gptnt.cli.checks.result import CheckResult
from gptnt.common.runtime_settings import RuntimeSettings
from gptnt.observability.settings import ObservabilitySettings

_NET_TIMEOUT = 3.0
# Refused/timed-out connects raise OSError/TimeoutError; a dead port-forward drops the stream
# (an anyio stream error).
_REDIS_PROBE_ERRORS = (OSError, TimeoutError, anyio.EndOfStream, anyio.BrokenResourceError)


async def _redis_pings(host: str, port: int) -> bool:
    """True iff a Redis answers its native PING health check (+PONG) at host:port.

    A port that merely accepts the TCP connection (e.g. a container runtime's port-forward with
    nothing behind it) is not a running Redis.
    """
    try:
        with anyio.fail_after(_NET_TIMEOUT):
            stream = await anyio.connect_tcp(host, port)
            async with stream:
                await stream.send(b"PING\r\n")
                reply = await stream.receive()
    except _REDIS_PROBE_ERRORS:
        return False
    return reply.startswith(b"+PONG")


async def _http_responds(url: str) -> bool:
    """True iff an HTTP server answers at `url` with any status (not a dead port-forward)."""
    try:
        async with httpx.AsyncClient(timeout=_NET_TIMEOUT) as client:
            _ = await client.get(url)
    except httpx.HTTPError:
        return False
    return True


async def check_redis(
    *,
    name: str = "Redis",
    hint: str = "Run a Redis here — e.g. `docker compose up -d`, or set REDIS_DSN to your own.",
) -> CheckResult:
    """Is a Redis actually answering at the configured DSN (via PING, not a bare port check)?"""
    parsed = urlsplit(str(RuntimeSettings().redis_dsn))
    host, port = parsed.hostname or "localhost", parsed.port or 6379
    if await _redis_pings(host, port):
        return CheckResult(name, "pass", f"reachable at {host}:{port}")
    return CheckResult(name, "fail", f"not reachable at {host}:{port}", hint)


async def check_em_port(
    *, kill_hint: str = "A stale process is squatting the port — clear it with: gptnt kill"
) -> CheckResult:
    """Port :8085 is free (the EM can start) or already serving a healthy EM."""
    runtime = RuntimeSettings()
    name = f"EM port :{runtime.em_port}"
    url = runtime.em_health_url
    try:
        async with httpx.AsyncClient(timeout=_NET_TIMEOUT) as client:
            response = await client.get(url)
    except (httpx.ConnectError, httpx.ConnectTimeout):
        # refused/timed-out/filtered connect == Nothing healthy is running here, so the EM can
        return CheckResult(name, "pass", "free (the EM can start here)")
    except httpx.HTTPError as exc:
        # connected, but mid-request timeout or not speaking HTTP
        return CheckResult(name, "fail", f"occupied, not responding: {exc}", kill_hint)
    if response.status_code == httpx.codes.OK:  # pyright: ignore[reportUnnecessaryComparison]
        return CheckResult(name, "pass", "an EM is already running and healthy")

    return CheckResult(name, "fail", f"occupied (HTTP {response.status_code})", kill_hint)


def _otel_host_port() -> tuple[str, int]:
    """Host/port for the OTLP collector, from `OTEL_EXPORTER_OTLP_ENDPOINT` or the default."""
    endpoint = ObservabilitySettings().otel_endpoint or "http://localhost:4318/"
    parsed = urlsplit(endpoint)
    return parsed.hostname or "localhost", parsed.port or 4318


async def check_observability(
    *,
    hint: str = "Optional — run a collector here (e.g. `docker compose up -d`) or set OTEL_EXPORTER_OTLP_ENDPOINT.",
) -> CheckResult:
    """Is an OTLP collector reachable? Recommended, not required — a warning, never a failure."""
    host, port = _otel_host_port()
    name = f"otel-collector :{port}"
    if await _http_responds(f"http://{host}:{port}/"):
        return CheckResult(name, "pass", f"reachable at {host}:{port}")
    return CheckResult(name, "warn", f"not reachable at {host}:{port}", hint)
