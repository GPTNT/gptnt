from typing import Literal

from pydantic.main import BaseModel
from pydantic.types import UUID4

from gptnt.api.experiment_manager.experiment_descriptor import ExperimentDescriptor
from gptnt.ktane.mission_spec import KtaneMissionSpec
from gptnt.ktane.state.bomb import BombState
from gptnt.players.spec import PlayerSpec


class BaseCommand(BaseModel, frozen=True):
    """Base class for commands sent through RabbitMQ."""


class StartExperimentCommand(BaseCommand, frozen=True):
    """Command to instruct room to start a new experiment.

    Connectivty:
    ```
    ┌────────┐     ┌────────┐
    │   EM   ┼────>│  Room  │
    └────────┘     └────────┘
    ```
    """

    command: Literal["start-experiment"] = "start-experiment"

    experiment_descriptor: ExperimentDescriptor


class StopExperimentCommand(BaseCommand, frozen=True):
    """Command to instruct a service to stop the currently running experiment.

    Connectivity:
    ```
    ┌────────┐     ┌────────┐      ┌───────────┐
    │   EM   ┼────>│  Room  ┼─┬──> │  Player  │
    └────────┘     └────────┘  │   └───────────┘
                              │   ┌────────┐
                              └──>│  Game  │
                                  └────────┘
    ```
    """

    command: Literal["stop-experiment"] = "stop-experiment"

    hard_crash: bool = False
    bomb_state: BombState | None = None


class ConfigurePlayerCommand(BaseCommand, frozen=True):
    """Command to instruct player to enter a certain configuration.

    Connectivity:
    ```
    ┌────────┐     ┌────────┐
    │  Room  ┼────>│ Player │
    └────────┘     └────────┘
    Handler should only return once the player is ready to start the experiment.
    ```
    """

    command: Literal["configure-player"] = "configure-player"

    player_spec: PlayerSpec
    experiment_descriptor: ExperimentDescriptor

    @property
    def room_uuid(self) -> UUID4:
        """Return the room UUID."""
        return self.experiment_descriptor.room_uuid

    @property
    def game_uuid(self) -> UUID4:
        """Return the game UUID."""
        return self.experiment_descriptor.game_uuid


class RunForwardOnceCommand(BaseCommand, frozen=True):
    """Command to instruct a player to run the forward pass once.

    Connectivity:
    ```
    ┌────────┐     ┌────────┐
    │  Room  ┼────>│ Player │
    └────────┘     └────────┘
    ```
    Handler should only return once the player has completed the forward pass.
    """

    command: Literal["run-forward-once"] = "run-forward-once"


class ReflectionCommand(BaseCommand, frozen=True):
    """Command to instruct a player to reflect on the game.

    Connectivity:
    ```
    ┌────────┐     ┌────────┐
    │  Room  ┼────>│ Player │
    └────────┘     └────────┘
    ```
    Handler should only return once the player has completed the reflection.
    """

    command: Literal["reflect"] = "reflect"
    reflection_message: str
    bomb_state: BombState | None = None


class ConfigureGameCommand(BaseCommand, frozen=True):
    """Command to instruct a game to enter a certain mission.

    Connectivity:
    ```
    ┌────────┐     ┌────────┐
    │  Room  ┼────>│  Game  │
    └────────┘     └────────┘
    ```
    Handler should only return once the game is ready to start the experiment.
    """

    command: Literal["configure-game"] = "configure-game"

    mission_spec: KtaneMissionSpec


class PauseGameCommand(BaseCommand, frozen=True):
    """Command to instruct game to pause the game.

    Connectivity:
    ```
    ┌────────┐     ┌────────┐
    │  Room  ┼────>│  Game  │
    └────────┘     └────────┘
    ```
    """

    command: Literal["pause-game"] = "pause-game"


class UnpauseGameCommand(BaseCommand, frozen=True):
    """Command to instruct game to un-pause the game.

    Connectivity:
    ```
    ┌────────┐     ┌────────┐
    │  Room  ┼────>│  Game  │
    └────────┘     └────────┘
    ```
    """

    command: Literal["unpause-game"] = "unpause-game"


class AdvanceTimeGameCommand(BaseCommand, frozen=True):
    """Command to instruct game to advance time.

    Connectivity:
    ```
    ┌────────┐     ┌────────┐
    │  Room  ┼────>│  Game  │
    └────────┘     └────────┘
    ```
    Handler should return once the game has advanced time.
    """

    command: Literal["advance-time"] = "advance-time"


class GameDoneCommand(BaseCommand, frozen=True):
    """Command to check if game is done.

    Connectivity:
    ```
    ┌────────┐     ┌────────┐
    │  Room  ┼────>│  Game  │
    └────────┘     └────────┘
    ```
    Handler should only return once the game is in GameState.game_ended
    """

    command: Literal["game-done"] = "game-done"


class GameGetObservationCommand(BaseCommand, frozen=True):
    """Command to request the game's current bomb-state and visuals.

    Connectivity:
    ```
    ┌────────┐     ┌────────┐
    │  Room  ┼────>│  Game  │
    └────────┘     └────────┘
    ```
    Handler should return game bomb state and visuals
    """

    command: Literal["game-get-observation"] = "game-get-observation"


class GameGetBombStateCommand(BaseCommand, frozen=True):
    """Command to request the game's current bomb-state.

    Connectivity:
    ```
    ┌────────┐     ┌────────┐
    │  Room  ┼────>│  Game  │
    └────────┘     └────────┘
    ```
    Handler should return game bomb state
    """

    command: Literal["game-get-bomb-state"] = "game-get-bomb-state"


RoomCommand = StartExperimentCommand | StopExperimentCommand
PlayerCommand = ConfigurePlayerCommand | StopExperimentCommand | ReflectionCommand
GameCommand = (
    ConfigureGameCommand
    | StopExperimentCommand
    | PauseGameCommand
    | UnpauseGameCommand
    | GameGetObservationCommand
    | AdvanceTimeGameCommand
    | GameGetBombStateCommand
)
