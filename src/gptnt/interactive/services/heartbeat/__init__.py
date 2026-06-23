from typing import Annotated

from pydantic import Tag

from gptnt.interactive.services.heartbeat.game import GameHeartbeat
from gptnt.interactive.services.heartbeat.player import PlayerHeartbeat

Heartbeat = Annotated[GameHeartbeat, Tag("game")] | Annotated[PlayerHeartbeat, Tag("player")]
