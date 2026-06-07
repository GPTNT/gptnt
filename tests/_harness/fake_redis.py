"""An in-process `fakeredis` server that clients connect to.

`TcpFakeServer` serves both the FastStream pub/sub RPC and the coredis heartbeat command set, provided the server is listening before any client connects.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from threading import Thread
from typing import TYPE_CHECKING, Any, override

from fakeredis import TcpFakeServer

from gptnt.core.common.servers import block_until_listening, get_available_port

if TYPE_CHECKING:
    from collections.abc import Iterator


class QuietTcpFakeServer(TcpFakeServer):
    """`TcpFakeServer` that swallows the broken-pipe noise clients cause on teardown.

    When brokers close their pub/sub connections during shutdown, the server's handler thread
    raises `BrokenPipeError` / `ConnectionResetError` mid-write and the default handler dumps a
    traceback to stderr.

    Those are harmless disconnects, so we silence those.
    """

    @override
    def handle_error(self, *args: Any, **kwargs: Any) -> None:
        if isinstance(sys.exception(), (BrokenPipeError, ConnectionResetError)):
            return
        super().handle_error(*args, **kwargs)


@contextmanager
def fake_redis_server() -> Iterator[str]:
    """Start an in-process fake Redis on a free port, yield its DSN, and tear it down after."""
    host, port = "127.0.0.1", get_available_port()
    server = QuietTcpFakeServer((host, port), server_type="redis")
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        block_until_listening(host, port)
        yield f"redis://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
