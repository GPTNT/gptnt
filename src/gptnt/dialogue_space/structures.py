from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel


class DialogueSpaceAgent(BaseModel):
    """Dialogue space representation of connected agent."""

    uuid: UUID
    last_read_message_id: int = -1
    is_player: bool = True


class DialogueSpaceMessage(BaseModel):
    """Dialogue space representation of agent message."""

    sender_uuid: UUID
    message_id: int
    message_content: str

    timestamp: datetime = datetime.now(tz=UTC)


class ClientRequest(BaseModel):
    """Generic client request data model."""

    uuid: UUID
    is_player: bool = True


class SendMessageData(ClientRequest):
    """Data sent by client when sending a message."""

    message: str
