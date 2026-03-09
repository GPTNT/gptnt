from typing import NamedTuple

from pydantic import UUID4, BaseModel, Field
from whenever import Instant

from gptnt.experiments.experiments import ExperimentSpec
from gptnt.ktane.mission_spec import KtaneMissionSpec
from gptnt.players.specification import CommunicationStyle, PlayerProtocol, PlayerRole


class PlayerContent(NamedTuple):
    """Simplify getting content about a player.

    This is more important for the expert since, if we don't do this, then there are just constant
    'if None' checks, which are just silly and annoying since we've already checked it.
    """

    protocol: PlayerProtocol
    name: str
    uuid: UUID4


class ExperimentDescriptor(BaseModel, frozen=True):
    """Describes a (running / finished) experiment.

    Includes the experiment specification and UUIDs of the players/room/game services.
    """

    experiment_spec: ExperimentSpec

    session_id: UUID4

    expert_uuid: UUID4 | None
    defuser_uuid: UUID4
    game_uuid: UUID4

    start_time: Instant = Field(default_factory=Instant.now)

    @property
    def name(self) -> str:
        """Get the detailed name of the experiment."""
        return self.experiment_spec.attempt_name

    @property
    def mission_spec(self) -> KtaneMissionSpec:
        """Get the mission spec for this experiment."""
        return self.experiment_spec.mission_spec

    @property
    def communication_style(self) -> CommunicationStyle:
        """Get the communication style for the experiment."""
        return self.experiment_spec.communication_style

    @property
    def some_player_wants_feedback(self) -> bool:
        """Check if any player wants feedback."""
        return self.experiment_spec.some_player_wants_feedback

    @property
    def player_uuids(self) -> list[UUID4]:
        """List of UUIDs for the players in this experiment."""
        player_uuids = [self.defuser_uuid]
        if self.expert_uuid:
            player_uuids.append(self.expert_uuid)
        return player_uuids

    @property
    def service_uuids(self) -> list[UUID4]:
        """List of UUIDs for the services in this experiment."""
        return [*self.player_uuids, self.game_uuid]

    @property
    def expert(self) -> PlayerContent | None:
        """Get the expert content for this experiment."""
        if (
            self.expert_uuid is None
            or self.experiment_spec.expert_protocol is None
            or self.experiment_spec.expert_name is None
        ):
            return None
        return PlayerContent(
            protocol=self.experiment_spec.expert_protocol,
            name=self.experiment_spec.expert_name,
            uuid=self.expert_uuid,
        )

    @property
    def defuser(self) -> PlayerContent:
        """Get the defuser content for this experiment."""
        return PlayerContent(
            protocol=self.experiment_spec.defuser_protocol,
            name=self.experiment_spec.defuser_name,
            uuid=self.defuser_uuid,
        )

    def get_uuid_for_other_role(self, *, current_role: PlayerRole) -> UUID4 | None:
        """Get the UUID for the other role in the experiment."""
        match current_role:
            case "defuser":
                return self.expert_uuid
            case "expert":
                return self.defuser_uuid

    def get_player_content_by_role(self, role: PlayerRole) -> PlayerContent:
        """Get the player content for the given role."""
        match role:
            case "defuser":
                return self.defuser
            case "expert":
                if self.expert is None:
                    raise ValueError("No expert configured for this experiment.")
                return self.expert
