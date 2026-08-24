from typing import NamedTuple

from pydantic import UUID4, ConfigDict, Field
from whenever import Instant

from gptnt.experiments.spec import ExperimentSpec
from gptnt.players.specification import PlayerCapabilities, PlayerProtocol, PlayerRole


class PlayerContent(NamedTuple):
    """The protocol, identity, and capabilities of one player in an experiment instance."""

    protocol: PlayerProtocol
    name: str
    uuid: UUID4
    capabilities: PlayerCapabilities


class ExperimentInstance(ExperimentSpec):
    """One execution of an experiment spec.

    It combines the requested mission and players with the service identities, resolved player
    capabilities, and start time used for that execution.
    """

    model_config = ConfigDict(frozen=True)

    session_id: UUID4
    """Identifier shared by the game and player records for this execution."""

    expert_uuid: UUID4 | None
    """Player-service process assigned to the expert role."""

    defuser_uuid: UUID4
    """Player-service process assigned to the defuser role."""

    game_uuid: UUID4
    """Game-service process assigned to this execution."""

    defuser_capabilities: PlayerCapabilities
    expert_capabilities: PlayerCapabilities | None

    start_time: Instant = Field(default_factory=Instant.now)
    """Instant used as the origin for relative step timestamps."""

    @property
    def player_uuids(self) -> list[UUID4]:
        """List the player service UUIDs."""
        player_uuids = [self.defuser_uuid]
        if self.expert_uuid:
            player_uuids.append(self.expert_uuid)
        return player_uuids

    @property
    def service_uuids(self) -> list[UUID4]:
        """List the player and game service UUIDs."""
        return [*self.player_uuids, self.game_uuid]

    @property
    def expert(self) -> PlayerContent | None:
        """Return the expert's runtime information when an expert is configured."""
        if (
            self.expert_uuid is None
            or self.expert_protocol is None
            or self.expert_name is None
            or self.expert_capabilities is None
        ):
            return None
        return PlayerContent(
            protocol=self.expert_protocol,
            name=self.expert_name,
            uuid=self.expert_uuid,
            capabilities=self.expert_capabilities,
        )

    @property
    def defuser(self) -> PlayerContent:
        """Return the defuser's runtime information."""
        return PlayerContent(
            protocol=self.defuser_protocol,
            name=self.defuser_name,
            uuid=self.defuser_uuid,
            capabilities=self.defuser_capabilities,
        )

    def get_uuid_for_other_role(self, *, current_role: PlayerRole) -> UUID4 | None:
        """Get the UUID for the other role in the experiment."""
        match current_role:
            case "defuser":
                return self.expert_uuid
            case "expert":
                return self.defuser_uuid

    def get_player_content_by_role(self, role: PlayerRole) -> PlayerContent:
        """Get the runtime information for one player role."""
        match role:
            case "defuser":
                return self.defuser
            case "expert":
                if self.expert is None:
                    raise ValueError("No expert configured for this experiment.")
                return self.expert
