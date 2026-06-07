import socket
from contextlib import closing
from time import monotonic


def get_available_port() -> int:
    """Return a random available port."""
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def block_until_listening(host: str, port: int, timeout: float = 5.0) -> None:
    """Block until a server is listening on the given host and port.

    Synchronous on purpose (uses `time.monotonic` rather than `anyio.current_time`) so it can
    be called outside an event loop.
    """
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            sock.settimeout(0.25)
            if sock.connect_ex((host, port)) == 0:
                return
    raise RuntimeError(f"server never started listening on {host}:{port}")
