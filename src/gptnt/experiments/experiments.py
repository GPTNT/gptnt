import itertools
from collections.abc import Iterator
from typing import Annotated, Literal, Self, override

from pydantic import BaseModel, BeforeValidator, model_validator

from gptnt.experiments.pairing import Pairing
from gptnt.ktane.mission_spec import KtaneMissionSpec
from gptnt.players.spec import CommunicationStyle, PlayerSpec

type Condition = Literal[
    "single_module",
    "multiple_modules_2",
    "multiple_modules_2_front",
    "multiple_modules_n",
    "multiple_modules_5",
    "repeated_modules_2",
    "repeated_modules_4",
]


class ExperimentSpec(BaseModel, frozen=True):
    """Specification for a single experiment.

    This contains everything that the Experiment Manager will need to run the experiment.
    """

    mission_spec: KtaneMissionSpec
    condition: Condition

    defuser_player_spec: PlayerSpec
    defuser_name: str

    expert_player_spec: PlayerSpec | None
    expert_name: str | None

    @model_validator(mode="after")
    def verify_expert_has_both_spec_and_name(self) -> Self:
        """Verify that the expert has both a spec and a name if they are set."""
        if self.expert_player_spec is None and self.expert_name is not None:
            raise ValueError("`expert_player_spec` must be set if `expert_name` is set.")
        if self.expert_player_spec is not None and self.expert_name is None:
            raise ValueError("`expert_name` must be set if `expert_player_spec` is set.")
        return self

    @model_validator(mode="after")
    def verify_no_expert_for_single_player(self) -> Self:
        """Verify that the expert is None if the defuser is a solo player."""
        if self.defuser_player_spec.is_solo_player and self.expert_player_spec is not None:
            raise ValueError("If the defuser is a solo player, then the expert must be None.")
        if self.defuser_player_spec.is_solo_player and self.expert_name is not None:
            raise ValueError("If the defuser is a solo player, then the expert_name must be None.")
        return self

    @property
    def is_single_player(self) -> bool:
        """Check if the experiment is a single player experiment."""
        return self.defuser_player_spec.is_solo_player

    @property
    def communication_style(self) -> CommunicationStyle:
        """Get the communication style for the experiment."""
        return self.defuser_player_spec.communication_style

    @property
    def pairing(self) -> str:
        """Get the names of the pair.

        Just to be consistent with the old way of doing it.
        """
        return f"{self._defuser_name}--{self._expert_name}"

    @property
    def experiment_name(self) -> str:
        """Get the name for the experiment."""
        module_names = "-".join(
            sorted({component.value for component in self.mission_spec.components})
        )
        return f"{self.condition}_{self.communication_style}_{module_names}_{self.mission_spec.seed}_({self.pairing})"

    @override
    def __hash__(self) -> int:
        return hash((self.mission_spec, self.pairing, self.condition, self.communication_style))

    @property
    def _defuser_name(self) -> str:
        """Get the name of the defuser with their thinking framework."""
        prefix = ""
        if self.defuser_player_spec.is_solo_player:
            prefix = "+solo"
        return f"defuser={self.defuser_name}{prefix}+{self.defuser_player_spec.thinking_framework}"

    @property
    def _expert_name(self) -> str:
        """Get the name of the expert with their thinking framework."""
        if self.expert_name is None or self.expert_player_spec is None:
            return "expert=None"
        return f"expert={self.expert_name}+{self.expert_player_spec.thinking_framework}"


class ExperimentGenerator(BaseModel):
    """Generate experiments from the given missions and pairings."""

    condition: Condition
    defuser_player_spec: PlayerSpec
    expert_player_spec: Annotated[
        PlayerSpec | None, BeforeValidator(lambda expert: expert if expert else None)
    ]

    def generate(
        self, missions: Iterator[KtaneMissionSpec], pairings: Iterator[Pairing]
    ) -> Iterator[ExperimentSpec]:
        """Generate all possible experiments to be run from the given inputs."""
        for mission, pairing in itertools.product(missions, pairings):
            if pairing.expert is not None and self.expert_player_spec is None:
                raise ValueError(
                    "If the expert is set in the pairing, then `expert_player_spec` must be set."
                )
            experiment = ExperimentSpec(
                mission_spec=mission,
                condition=self.condition,
                defuser_player_spec=self.defuser_player_spec,
                defuser_name=pairing.defuser,
                expert_player_spec=self.expert_player_spec,
                expert_name=pairing.expert,
            )
            yield experiment
