from asyncio import Event, Task, create_task
from types import TracebackType
from typing import Any, Self

from structlog import get_logger
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed
from websockets.protocol import State

from gptnt.websocket_api.exceptions import InvalidConnectionError, InvalidRequestIDError
from gptnt.websocket_api.structures import WebsocketRequest, WebsocketResponse


class WebsocketClient:
    """Base class for websocket based clients.

    Implements client->server connection and endpoint wrapping. Uses a trivial constructor to
    initialise config, so to begin the connection you MUST await `.connect()`.
    """

    def __init__(self, host: str, port: int) -> None:
        self.uri: str = f"ws://{host}:{port}"
        self.current_request_id: int = 0
        self.pending_requests: dict[str, Event] = {}
        self.pending_responses: dict[str, Any] = {}
        self.connection: None | ClientConnection = None
        self.response_task: None | Task[None] = None
        self._logger = get_logger()

    @property
    def is_connected(self) -> bool:
        """Check if the client is currently connected to the server."""
        return self.connection is not None and self.connection.state is State.OPEN

    async def __aenter__(self) -> Self:
        """Safe async context entering logic."""
        _ = await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ) -> None:
        """Safe async context exiting logic."""
        await self.close()

    async def connect(self) -> Self:
        """Open the connection to the WebsocketServer."""
        self.connection = await connect(self.uri)
        self.response_task = create_task(self._response_handler())
        return self  # Chaining

    async def close(self) -> None:
        """Close the connection."""
        if self.response_task and not self.response_task.done():
            _ = self.response_task.cancel()

        if self.connection:
            await self.connection.close()

    def send_request(self, endpoint: str, data: Any) -> Task[Any]:
        """Request data from the websocket endpoint."""
        # Schedule the request send to be executed immediately and return a promise to the response data
        return create_task(self._send_request_handler(endpoint, data))

    async def _send_request_handler(self, endpoint: str, data: Any) -> Any:
        if self.connection is None:
            raise InvalidConnectionError

        request_id = self._get_new_request_id()

        # Create a sync primitive to later await on server response
        self.pending_requests[request_id] = Event()

        # Wrap data in request frame and send to server
        request = WebsocketRequest(
            request_id=request_id, endpoint=endpoint, data=data
        ).model_dump_json()
        await self.connection.send(request)

        # Wait on server response
        _ = await self.pending_requests[request_id].wait()
        _ = self.pending_requests.pop(request_id)

        # Return the response from the server
        response = self.pending_responses[request_id]
        self.pending_responses.pop(request_id)
        return response

    def _get_new_request_id(self) -> str:
        """Get a new unique id to tag request (generated using a simple counter)."""
        self.current_request_id += 1
        return str(self.current_request_id)

    async def _response_handler(self) -> None:  # noqa: WPS231 - This function is not complex
        """Handles responses from the server and awakens waiting request co-routines."""
        while True:
            if not self.connection:
                # If the connection closes immediately dont wait on any messages
                return

            try:
                response = await self.connection.recv()
            except ConnectionClosed:
                self.connection = None
                self._logger.info("Websocket connection to client closed", uri=self.uri)

                # Connection no longer exists, return from the handler coroutine
                return

            # Might throw ValidationError
            parsed = WebsocketResponse.model_validate_json(json_data=response, strict=True)

            if parsed.request_id not in self.pending_requests:
                # This suggests a major issue with server code, and is unrecoverable
                raise InvalidRequestIDError

            # Pass through the response data and awaken waiting request coroutine
            self.pending_responses[parsed.request_id] = parsed.data
            self.pending_requests[parsed.request_id].set()
