from dataclasses import dataclass, field
from uuid import uuid4

from pydantic import UUID4

from gptnt.players.ai.action_predictor import ActionPredictor
from gptnt.players.ai.input_builder import AgentInputBuilder
from gptnt.players.ai.message_history import MessageHistory
from gptnt.players.metrics.episode_tracker import EpisodeTracker
from gptnt.players.observation_handler import ObservationHandler
from gptnt.players.specification import PlayerCapabilities, PlayerProtocol
from gptnt.services.events.player import PlayerState
from gptnt.services.experiment_descriptor import ExperimentDescriptor
from gptnt.services.game.client import GameClient
from gptnt.services.player.action_dispatcher import ActionDispatcher
from gptnt.services.player.message_handler import MessageManager


@dataclass(kw_only=True)
class PlayerServiceState:
    """State for the player service.

    To keep things more simpler, this class just holds the various aspects in a way that is easy to
    grab. We are not doing any logic or processing here, as that should be done in the various
    routes of the service.

    I'm hoping that in this way, we can keep things clearer but also nice and explicit about what
    is happening and who is doing what by deferring ALL of that logic to the various components and
    the API routes that use them.
    """

    uuid: UUID4 = field(default_factory=uuid4)

    capabilities: PlayerCapabilities
    service_name: str = field(init=False)
    state: PlayerState = field(default=PlayerState.idle, init=False)
    observation_handler: ObservationHandler
    action_predictor: ActionPredictor

    action_dispatcher: ActionDispatcher = field(init=False, repr=False)
    game_client: GameClient = field(default_factory=GameClient)

    # Components that need to be reset after each experiment
    episode_tracker: EpisodeTracker
    message_manager: MessageManager = field(default_factory=MessageManager)

    # This is set when the player is configured for an experiment
    experiment_descriptor: ExperimentDescriptor = field(init=False, repr=False)
    protocol: PlayerProtocol = field(init=False, repr=False)
    message_history: MessageHistory = field(init=False, repr=False)
    input_builder: AgentInputBuilder = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Setup the service."""
        # super().__post_init__()
        self.service_name = self.capabilities.player_name

        self.action_dispatcher = ActionDispatcher(
            tracker=self.episode_tracker,
            observation_handler=self.observation_handler,
            game_client=self.game_client,
            message_manager=self.message_manager,
        )

    def reset(self) -> None:
        """Reset the player service state for a new experiment."""
        self.state = PlayerState.cleanup
        self.message_manager.reset()
        self.game_client.clear_client_url()
        self.observation_handler.reset()
        self.episode_tracker.reset()
        self.state = PlayerState.idle
