from asyncio import Task, create_task
from collections.abc import Callable
from types import TracebackType
from typing import TYPE_CHECKING, Any, Self

from structlog import get_logger
from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed

from gptnt.websocket_api.exceptions import InvalidEndpointError
from gptnt.websocket_api.structures import WebsocketRequest, WebsocketResponse

if TYPE_CHECKING:
    from websockets import Server


class WebsocketServer:
    """Base class for websocket based servers.

    Implements server connections and event handling. Uses a trivial constructor to initialise
    config, so to start serving you MUST await `.start()`.
    """

    def __init__(self, host: str, port: int) -> None:
        self.host: str = host
        self.port: int = port
        self.server: None | Server = None
        self.callbacks: dict[str, Callable[..., Any]] = {}
        self.serving: None | Task[None] = None
        self._logger = get_logger()

    async def __aenter__(self) -> Self:
        """Safe async context entering logic."""
        _ = await self.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ) -> None:
        """Safe async context exiting logic."""
        await self.stop()

    def on(self, endpoint: str, callback: Callable[..., Any]) -> None:
        """Specifies the callback for the passed endpoint."""
        self.callbacks[endpoint] = callback

    async def start(self) -> Self:
        """Starts the server."""
        server_init = serve(handler=self._connection_handler, host=self.host, port=self.port)
        self.server = await server_init
        self.serving = create_task(self.server.serve_forever())
        return self  # Chaining

    async def stop(self) -> None:
        """Stop serving."""
        if self.serving and not self.serving.done():
            _ = self.serving.cancel()

        if self.server:
            self.server.close()
            for connection in self.server.connections:
                await connection.close()

    async def _connection_handler(self, connection: ServerConnection) -> None:
        """Handles a single incoming connection and detects disconnects."""
        # For each incoming request, switch to user-defined handler
        while True:
            try:
                message = await connection.recv()
            except ConnectionClosed:
                # TODO: Contact controller?
                self._logger.info(
                    "Websocket connection to server closed",
                    server_uri=f"{self.host}:{self.port}",
                    client_id=connection.id,
                )

                # Connection no longer exists, return from this handler
                return

            # Can throw ValidationError
            parsed = WebsocketRequest.model_validate_json(json_data=message, strict=True)

            if parsed.endpoint in self.callbacks:
                # Call corresponding handler, and copy returned data into the response
                response_data = self.callbacks.get(parsed.endpoint, lambda _: None)(parsed.data)
                response = WebsocketResponse(
                    status="success", request_id=parsed.request_id, data=response_data
                )

                # Send back response
                await connection.send(response.model_dump_json())

            else:
                response = WebsocketResponse(
                    status="invalid_endpoint", request_id=parsed.request_id, data=None
                )
                self._logger.info(
                    "Invalid endpoint accessed on websocket server",
                    server_uri=f"{self.host}:{self.port}",
                    client_id=connection.id,
                    endpoint=parsed.endpoint,
                )
                raise InvalidEndpointError(parsed.endpoint)
