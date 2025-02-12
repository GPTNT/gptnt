from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel


# Agents
class DialogueSpaceAgent(BaseModel):
    """Dialogue space representation of connected agent."""

    uuid: UUID
    last_read_message: int = -1


# Messages
class DialogueSpaceMessage(BaseModel):
    """Dialogue space representation of agent message."""

    # Message content
    sender_uuid: UUID
    message_id: int
    message_content: str

    # Metadata (Used for filtering, telemetry, etc.)
    timestamp: datetime = datetime.now(tz=UTC)


# Requests
class ClientRequest(BaseModel):
    """Generic client request data model."""

    uuid: UUID


class SendMessageData(ClientRequest):
    """Data sent by client when sending a message."""

    message: str
