from enum import Enum

from pydantic import BaseModel


class RoomStage(Enum):
    """The stage of the experiment lifecycle that a RoomManager is in."""

    boot = "boot"
    """RoomManager is still starting."""

    ready_for_config = "ready_for_config"
    """The RoomManager is ready to receive a mission config and players."""

    ready_for_start = "ready_for_start"
    """The RoomManager is ready to start the mission (players connected)."""

    in_experiment = "in_experiment"
    """The RoomManager is currently playing a mission."""

    done = "done"
    """The RoomManager is finished playing a mission."""


class ClientMetadata(BaseModel):
    """Metadata for a given client."""

    fastapi_url: str
    """The URL of the FastAPI server that it's running on."""


class RoomMetadata(ClientMetadata):
    """Information about a Room that needed to maintain a connection."""

    dialogue_space_url: str
    ktane_url: str
    state: RoomStage


class PlayerMetadata(ClientMetadata):
    """Information about a PlayerAPI needed to maintain a connection."""

    player_type: str
    player_role: str
