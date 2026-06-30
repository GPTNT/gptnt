from typing import Self, override

from pydantic import BaseModel, model_validator

from gptnt.ktane.mission_spec import KtaneMissionSpec
from gptnt.specification import CommunicationStyle, PlayerProtocol, PlayerRole


class ExperimentSpec(BaseModel, frozen=True):
    """Specification for a single experiment.

    This contains everything that the Experiment Manager will need to run the experiment.
    """

    mission_spec: KtaneMissionSpec
    mission_set: str
    """The mission set this came from (the `missions_path` basename), e.g. `single_module`."""

    attempt: int = 1

    suite_id: str = "unknown"
    """The suite this spec was generated for."""

    suite_revision: int = 0
    """The suite revision at generation time."""

    defuser_protocol: PlayerProtocol
    defuser_name: str

    expert_protocol: PlayerProtocol | None
    expert_name: str | None

    @model_validator(mode="after")
    def verify_expert_has_both_spec_and_name(self) -> Self:
        """Verify that the expert has both a spec and a name if they are set."""
        if self.expert_protocol is None and self.expert_name is not None:
            raise ValueError("`expert_protocol` must be set if `expert_name` is set.")
        if self.expert_protocol is not None and self.expert_name is None:
            raise ValueError("`expert_name` must be set if `expert_protocol` is set.")
        return self

    @model_validator(mode="after")
    def verify_no_expert_for_single_player(self) -> Self:
        """Verify that the expert is None if the defuser is a solo player."""
        if self.defuser_protocol.is_solo_player and self.expert_protocol is not None:
            raise ValueError("If the defuser is a solo player, then the expert must be None.")
        if self.defuser_protocol.is_solo_player and self.expert_name is not None:
            raise ValueError("If the defuser is a solo player, then the expert_name must be None.")
        return self

    @property
    def is_single_player(self) -> bool:
        """Check if the experiment is a single player experiment."""
        return self.defuser_protocol.is_solo_player

    @property
    def communication_style(self) -> CommunicationStyle:
        """Get the communication style for the experiment."""
        return self.defuser_protocol.communication_style

    @property
    def pairing(self) -> str:
        """Get the names of the pair.

        Just to be consistent with the old way of doing it.
        """
        return f"{self._defuser_name}--{self._expert_name}"

    @property
    def suite_version(self) -> str:
        """Get the suite version for the experiment."""
        return f"{self.suite_id}[rev{self.suite_revision}]"

    @property
    def experiment_name(self) -> str:
        """Get the name for the experiment."""
        module_names = "-".join(
            sorted({component.value for component in self.mission_spec.components})
        )
        return "_".join(
            [
                self.suite_version,
                self.mission_set,
                self.communication_style,
                module_names,
                str(self.mission_spec.seed),
                f"({self.pairing})",
            ]
        )

    @property
    def attempt_name(self) -> str:
        """Get the name for the attempt."""
        return f"{self.experiment_name}_attempt{self.attempt}"

    @property
    def some_player_wants_feedback(self) -> bool:
        """Check if any player wants feedback."""
        defuser_wants_feedback = self.defuser_protocol.receive_feedback_after_action
        expert_wants_feedback = (
            self.expert_protocol.receive_feedback_after_action if self.expert_protocol else False
        )
        return defuser_wants_feedback or expert_wants_feedback

    @override
    def __hash__(self) -> int:
        return hash(
            (
                self.mission_spec,
                self.pairing,
                self.mission_set,
                self.communication_style,
                self.attempt,
            )
        )

    def get_player_protocol(self, role: PlayerRole) -> PlayerProtocol | None:
        """Get the player protocol for the given role."""
        match role:
            case "defuser":
                return self.defuser_protocol
            case "expert":
                return self.expert_protocol

    @property
    def _defuser_name(self) -> str:
        """Get the name of the defuser with their thinking framework."""
        prefix = ""
        if self.defuser_protocol.is_solo_player:
            prefix = f"{prefix}+solo"
        if self.defuser_protocol.include_manual:
            prefix = f"{prefix}+manual"
        return f"defuser={self.defuser_name}{prefix}"

    @property
    def _expert_name(self) -> str:
        """Get the name of the expert with their thinking framework."""
        if self.expert_name is None or self.expert_protocol is None:
            return "expert=None"
        return f"expert={self.expert_name}"
