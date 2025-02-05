from pydantic import BaseModel, ConfigDict


class WebsocketRequest[dtype](BaseModel):
    """Generic request through the websocket API."""

    model_config = ConfigDict(strict=True)

    # Fields
    request_id: str  # Client-chosen endpoint to match request to response
    endpoint: str  # Endpoint name
    data: dtype  # Arbitrary data


class WebsocketResponse[dtype](BaseModel):
    """Generic response through the websocket API."""

    model_config = ConfigDict(strict=True)

    # Fields
    request_id: str  # Client-chosen id to match response to request
    status: str  # TODO: define these [TNT-XXX]
    data: dtype  # Arbitrary data
