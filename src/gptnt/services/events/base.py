from pydantic import UUID4, BaseModel


class BaseEvent(BaseModel, frozen=True):
    """Base class for events sent from services to the EM across RabbitMQ."""

    uuid: UUID4
    """UUID of the service sending the event."""

    service_name: str
    """Service name."""
