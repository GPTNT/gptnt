from pydantic import UUID4, BaseModel, Field


class BaseEvent(BaseModel, frozen=True):
    """Base class for events sent from services to the EM across RabbitMQ."""

    uuid: UUID4
    """UUID of the service sending the event."""

    service_name: str
    """Service name."""


class Response[DataType](BaseModel, frozen=True):
    """Base class for responses sent from services to the EM across RabbitMQ."""

    data: DataType

    success: bool = True
    """Whether the request was successful."""

    headers: dict[str, str] = Field(default_factory=dict)
    """Optional headers for the response."""

    detail: str | None = None
