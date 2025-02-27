class InvalidConnectionError(Exception):
    """Exception for attempting to send a request without connection to the server first."""

    def __init__(self) -> None:
        super().__init__(
            "No connection with server, make sure to call `client.connect()` before sending requests"
        )


class InvalidRequestIDError(Exception):
    """Exception for client receiving a response to a request it did not send."""

    def __init__(self) -> None:
        super().__init__("Invalid request_id received")


class InvalidEndpointError(Exception):
    """Exception for attempting to call the callback for a non-existent endpoint."""

    def __init__(self, endpoint: str) -> None:
        super().__init__(f"Invalid endpoint: {endpoint}")
        self.endpoint = endpoint
