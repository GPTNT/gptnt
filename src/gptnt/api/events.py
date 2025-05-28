from typing import Annotated, Literal

from pydantic import Field, Tag
from pydantic.main import BaseModel
from pydantic.types import UUID4, Base64Str

from gptnt.api.experiment_manager.experiment_descriptor import ExperimentDescriptor
from gptnt.players.spec import PlayerMetadata


class BaseEvent(BaseModel, frozen=True):
    """Base class for events sent from services to the EM across RabbitMQ."""

    uuid: UUID4
    """UUID of the service sending the event."""


class HeartbeatEvent(BaseEvent, frozen=True):
    """Event for tracking heartbeats.

    Connectivity:
    ```
    ┌────────┐
    │ Player ┼─┐
    └────────┘ │
    ┌────────┐ │   ┌────────┐
    │  Game  ┼─┼──>│   EM   │
    └────────┘ │   └────────┘
    ┌────────┐ │
    │  Room  ┼─┘
    └────────┘
    ```
    Handler should always return immediately.
    """

    event: Literal["heartbeat"] = "heartbeat"

    opt: Base64Str = ""


class ReadyEvent(BaseEvent, frozen=True):
    """Event for a service to indicate that it is ready for an experiment.

    Connectivity:
    ```
    ┌────────┐
    │ Player ┼─┐
    └────────┘ │
    ┌────────┐ │   ┌────────┐
    │  Game  ┼─┼──>│   EM   │
    └────────┘ │   └────────┘
    ┌────────┐ │
    │  Room  ┼─┘
    └────────┘
    ```
    """

    event: Literal["ready"] = "ready"


class NotReadyEvent(BaseEvent, frozen=True):
    """Event for a service to indicate that it is no longer ready for an experiment.

    Could be due to a game crash or human player closing the UI. If this is sent while
    the service is in an experiment then the experiment will be stopped.

    Connectivity:
    ```
    ┌────────┐     ┌────────┐
    │ Player ┼─┬──>│   EM   │
    └────────┘ │   └────────┘
    ┌────────┐ │
    │  Game  ┼─┘
    └────────┘
    ```
    """

    event: Literal["not-ready"] = "not-ready"


class PlayerConnectEvent(BaseEvent, frozen=True):
    """Event for player service connecting to EM.

    Connectivity:
    ```
    ┌────────┐     ┌────────┐
    │ Player ┼────>│   EM   │
    └────────┘     └────────┘
    ```
    """

    event: Literal["player-connect"] = "player-connect"

    metadata: PlayerMetadata


class GameConnectEvent(BaseEvent, frozen=True):
    """Event for game service connecting to EM.

    Connectivity:
    ```
    ┌────────┐     ┌────────┐
    │  Game  ┼────>│   EM   │
    └────────┘     └────────┘
    ```
    """

    event: Literal["game-connect"] = "game-connect"


class RoomConnectEvent(BaseEvent, frozen=True):
    """Event for room service connecting to EM.

    Connectivty:
    ```
    ┌────────┐     ┌────────┐
    │  Room  ┼────>│   EM   │
    └────────┘     └────────┘
    ```
    """

    event: Literal["room-connect"] = "room-connect"


class ExperimentDoneEvent(BaseEvent, frozen=True):
    """Event for room service signaling experiment completion to EM.

    Connectivty:
    ```
    ┌────────┐     ┌────────┐
    │  Room  ┼────>│   EM   │
    └────────┘     └────────┘
    ```
    """

    event: Literal["experiment-done"] = Field(default="experiment-done", init=False)

    experiment_descriptor: ExperimentDescriptor
    hard_crash: bool
    """Did the experiment finish successfully, if true this experiment needs to run again."""


ConnectEvent = (
    Annotated[PlayerConnectEvent, Tag("player")]
    | Annotated[GameConnectEvent, Tag("game")]
    | Annotated[RoomConnectEvent, Tag("room")]
)
ReadinessEvent = Annotated[ReadyEvent, Tag("ready")] | Annotated[NotReadyEvent, Tag("not-ready")]
