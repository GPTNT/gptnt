from dataclasses import dataclass

from faststream.rabbit import ExchangeType, RabbitBroker, RabbitExchange
from pydantic.types import UUID4

from gptnt.api.commands import (
    GameCommand,
    GameDoneCommand,
    PlayerCommand,
    RoomCommand,
    RunForwardOnceCommand,
)
from gptnt.api.events import ConnectEvent, ExperimentDoneEvent, HeartbeatEvent, ReadinessEvent
from gptnt.api.rabbit import APIQueue, APIRoute
from gptnt.experiments.experiments import ExperimentSpec
from gptnt.ktane.actions import KtaneAction
from gptnt.ktane.client import ObservationFrames
from gptnt.ktane.state.bomb import BombState
from gptnt.players.spec import PlayerRole

# Acknowledge
acknowledge = RabbitExchange(name="acknowledge", type=ExchangeType.TOPIC)

# Experiment
experiment_connections = RabbitExchange(name="experiment.connections", type=ExchangeType.TOPIC)
experiment_command = RabbitExchange(name="experiment.command", type=ExchangeType.TOPIC)
experiment_heartbeat = RabbitExchange(name="experiment.heartbeat", type=ExchangeType.TOPIC)
experiment_ready = RabbitExchange(name="experiment.ready", type=ExchangeType.TOPIC)
experiment_specs = RabbitExchange(name="experiment.specs", type=ExchangeType.TOPIC)


# Game
game_actions = RabbitExchange(name="game.actions", type=ExchangeType.TOPIC)
game_messages = RabbitExchange(name="game.messages", type=ExchangeType.TOPIC)
game_observations = RabbitExchange(name="game.observations", type=ExchangeType.TOPIC)


@dataclass(kw_only=True)
class APIQueues:
    """Collection of all queues in the API."""

    broker: RabbitBroker

    def experiment_heartbeat(self) -> APIQueue[HeartbeatEvent]:
        """Heartbeat queue for experiment section."""
        return APIQueue(
            broker=self.broker, exchange=experiment_heartbeat, queue_name="experiment.heartbeat"
        )

    def experiment_connections(self) -> APIQueue[ConnectEvent]:
        """Connection queue for the experiment manager."""
        return APIQueue(
            broker=self.broker,
            exchange=experiment_connections,
            queue_name="experiment.connections",
        )

    def experiment_done(self) -> APIQueue[ExperimentDoneEvent]:
        """Done event queue from room to experiment manager."""
        return APIQueue(
            broker=self.broker, exchange=experiment_command, queue_name="experiment.done"
        )

    def experiment_ready(self) -> APIQueue[ReadinessEvent]:
        """Ready event queue from services to EM."""
        return APIQueue(
            broker=self.broker, exchange=experiment_ready, queue_name="experiment.ready"
        )

    def experiment_specs(self) -> APIQueue[list[ExperimentSpec]]:
        """Experiment specs queue for the experiment manager."""
        return APIQueue(
            broker=self.broker, exchange=experiment_specs, queue_name="experiment.specs"
        )

    def player_command(self, player_uuid: UUID4) -> APIQueue[PlayerCommand]:
        """Command queue for a player."""
        return APIQueue(
            broker=self.broker,
            exchange=experiment_command,
            queue_name=f"player.{player_uuid}.command",
        )

    def player_run(self, player_uuid: UUID4) -> APIQueue[RunForwardOnceCommand]:
        """Command queue for run commands from room to player."""
        return APIQueue(
            broker=self.broker, exchange=experiment_command, queue_name=f"player.{player_uuid}.run"
        )

    def player_messages(self, player_uuid: UUID4) -> APIQueue[str]:
        """Message queue for a player."""
        return APIQueue(
            broker=self.broker, exchange=game_messages, queue_name=f"player.{player_uuid}.messages"
        )

    def player_observations(self, player_uuid: UUID4) -> APIQueue[str]:
        """Message queue for a player."""
        return APIQueue(
            broker=self.broker,
            exchange=game_observations,
            queue_name=f"player.{player_uuid}.observations",
        )

    def game_actions(self, game_uuid: UUID4) -> APIQueue[KtaneAction]:
        """Action queue for a game."""
        return APIQueue[KtaneAction](
            broker=self.broker, exchange=game_actions, queue_name=f"game.{game_uuid}.actions"
        )

    def game_command(self, game_uuid: UUID4) -> APIQueue[GameCommand]:
        """Command queue for a game."""
        return APIQueue(
            broker=self.broker, exchange=experiment_command, queue_name=f"game.{game_uuid}.command"
        )

    def game_done(self, game_uuid: UUID4) -> APIQueue[GameDoneCommand]:
        """Command queue for game done checks from room."""
        return APIQueue(
            broker=self.broker, exchange=experiment_command, queue_name=f"game.{game_uuid}.done"
        )

    def room_command(self, room_uuid: UUID4) -> APIQueue[RoomCommand]:
        """Command queue for a room."""
        return APIQueue(
            broker=self.broker, exchange=experiment_command, queue_name=f"room.{room_uuid}.command"
        )


@dataclass(kw_only=True)
class APIRoutes:
    """Collection of all the dynamic routes in the API.

    Basically any route that does not target a single queue, or that is changed during runtime.
    """

    broker: RabbitBroker

    def game_observations(self, game_uuid: UUID4) -> APIRoute[BombState | ObservationFrames]:
        """Dynamic route for publishing observations to all defuser players in a game."""
        return APIRoute(
            broker=self.broker,
            exchange=game_observations,
            routing_key=f"game.{game_uuid}.observations",
        )

    def game_messages(self, game_uuid: UUID4, role: PlayerRole) -> APIRoute[str]:
        """Dynamic route for publishing messages to all players of a specific role in a game."""
        return APIRoute(
            broker=self.broker,
            exchange=game_messages,
            routing_key=f"game.{game_uuid}.role.{role}.messages",
        )
