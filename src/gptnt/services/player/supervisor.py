from dataclasses import dataclass, field
from typing import override
from uuid import uuid4

import structlog
from pydantic import UUID4

from gptnt.players.ai.action_predictor import ActionPredictor
from gptnt.players.ai.input_builder import AgentInputBuilder
from gptnt.players.ai.message_history import MessageHistory
from gptnt.players.metrics.recorder import ExperimentPlayerRecorder
from gptnt.players.observation_handler import ObservationHandler
from gptnt.players.specification import PlayerCapabilities, PlayerProtocol
from gptnt.services.events.heartbeat import PlayerHeartbeat
from gptnt.services.events.player import PlayerState
from gptnt.services.experiment_descriptor import ExperimentDescriptor
from gptnt.services.game.client import GameClient
from gptnt.services.heartbeat_broadcaster import HeartbeatBroadcaster
from gptnt.services.player.action_dispatcher import ActionDispatcher
from gptnt.services.player.message_handler import IncomingMessageHandler


@dataclass(kw_only=True)
class PlayerSupervisor(HeartbeatBroadcaster):
    """Supervisor for the player.

    Just brings together the various components with the heartbeat to form the main player service.
    No logic is done here, that's delegated to the various routes done elsewhere.

    I'm hoping that in this way, we can keep things clearer but also nice and explicit about what
    is happening and who is doing what by deferring ALL of that logic to the various components and
    the API routes that use them.
    """

    uuid: UUID4 = field(default_factory=uuid4)

    capabilities: PlayerCapabilities
    service_name: str = field(init=False)
    observation_handler: ObservationHandler
    action_predictor: ActionPredictor
    action_dispatcher: ActionDispatcher = field(init=False, repr=False)
    game_client: GameClient = field(default_factory=GameClient)

    # Components that need to be reset after each experiment
    experiment_recorder: ExperimentPlayerRecorder
    incoming_message_handler: IncomingMessageHandler = field(
        default_factory=IncomingMessageHandler
    )

    # This is set when the player is configured for an experiment
    experiment_descriptor: ExperimentDescriptor = field(init=False, repr=False)
    protocol: PlayerProtocol = field(init=False, repr=False)
    message_history: MessageHistory = field(init=False, repr=False)
    input_builder: AgentInputBuilder = field(init=False, repr=False)

    _state: PlayerState = field(default=PlayerState.idle, init=False)

    def __post_init__(self) -> None:
        """Setup the service."""
        self.service_name = self.capabilities.player_name

        self.action_dispatcher = ActionDispatcher(
            observation_handler=self.observation_handler,
            game_client=self.game_client,
            incoming_message_handler=self.incoming_message_handler,
        )

        self.validate_configuration()

    @property
    def state(self) -> PlayerState:
        """Get the current state of the player."""
        return self._state

    @state.setter
    def state(self, state: PlayerState) -> None:
        """Set the current state of the player."""
        self._state = state
        _ = structlog.contextvars.bind_contextvars(player_state=self._state.name)

    @override
    def heartbeat_event(self) -> PlayerHeartbeat:
        """Create the connect event for this service that gets sent on start."""
        return PlayerHeartbeat(
            uuid=self.uuid,
            service_name=self.service_name,
            state=self.state,
            ready_state=self.ready_state,
            capabilities=self.capabilities,
        )

    def reset(self) -> None:
        """Reset the player service state for a new experiment."""
        self.state = PlayerState.cleanup
        self.incoming_message_handler.reset()
        self.observation_handler.reset()
        self.experiment_recorder.reset()
        self.state = PlayerState.idle

    def validate_configuration(self) -> None:
        """Validate the player configuration and setup."""
        if (
            self.capabilities.interaction_location_method == "coordinates"
            and self.observation_handler.image_resizer is None
        ):
            raise ValueError(
                "Players using coordinate-based interaction must have an image resizer configured."
            )

        if (
            self.capabilities.interaction_location_method == "set-of-marks"
            and self.observation_handler.set_of_marks_painter is None
        ):
            raise ValueError(
                "Players using set-of-marks interaction must have a set-of-marks painter configured."
            )
