from pydantic import BaseModel
from pydantic.fields import computed_field
from pydantic.types import UUID4

from gptnt.experiments.experiments import ExperimentSpec
from gptnt.players.spec import CommunicationStyle


class ExperimentDescriptor(BaseModel, frozen=True):
    """Describes a (running / finished) experiment.

    Includes the experiment specification and UUIDs of the players/room/game services.
    """

    experiment_spec: ExperimentSpec

    experiment_id: UUID4
    """Unique identifier for the experiment being run."""

    expert_uuid: UUID4 | None
    defuser_uuid: UUID4
    game_uuid: UUID4
    room_uuid: UUID4

    @computed_field
    @property
    def service_uuids(self) -> list[UUID4]:
        """List of UUIDs for the services in this experiment."""
        services = [self.defuser_uuid, self.game_uuid, self.room_uuid]
        if self.expert_uuid:
            services.append(self.expert_uuid)
        return services

    @property
    def communication_style(self) -> CommunicationStyle:
        """Get the communication style for the experiment."""
        return self.experiment_spec.communication_style
