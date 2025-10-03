from dataclasses import dataclass
from typing import override

from gptnt.services.events.heartbeat import PlayerHeartbeat
from gptnt.services.heartbeat_broadcaster import HeartbeatBroadcaster
from gptnt.services.player.state import PlayerServiceState


@dataclass(kw_only=True)
class PlayerSupervisor(PlayerServiceState, HeartbeatBroadcaster):
    """Supervisor for the player."""

    @override
    def heartbeat_event(self) -> PlayerHeartbeat:
        """Create the connect event for this service that gets sent on start."""
        return PlayerHeartbeat(
            uuid=self.uuid,
            service_name=self.service_name,
            state=self.state,
            ready_state=self.ready_state,
            url=self.url,
            capabilities=self.capabilities,
        )
