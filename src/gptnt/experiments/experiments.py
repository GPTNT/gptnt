import itertools
from collections.abc import Iterator
from typing import Literal, override

from pydantic import BaseModel

from gptnt.experiments.pairing import Pairing
from gptnt.ktane.mission_spec import KtaneMissionSpec

type CommunicationStyle = Literal["parallel", "sequential"]

type Condition = Literal[
    "single_module",
    "multiple_modules_2",
    "multiple_modules_2_front",
    "multiple_modules_n",
    "multiple_modules_5",
    "repeated_modules_2",
    "repeated_modules_5",
]


class ExperimentSpec(BaseModel, frozen=True):
    """Specification for a single experiment.

    This contains everything that the Experiment Manager will need to run the experiment.
    """

    mission_spec: KtaneMissionSpec
    pairing: Pairing
    condition: Condition
    communication_style: CommunicationStyle

    @property
    def experiment_name(self) -> str:
        """Get the name for the experiment."""
        module_names = "-".join(
            sorted({component.value for component in self.mission_spec.components})
        )
        mission_name = f"{module_names}_{self.mission_spec.seed}"
        return f"{self.condition}_{self.communication_style}_{self.pairing}_{mission_name}"

    @override
    def __hash__(self) -> int:
        return hash((self.mission_spec, self.pairing, self.condition, self.communication_style))


class ExperimentGenerator:
    """Generate experiments from the given missions and pairings."""

    def __init__(self, *, condition: Condition, communication_style: CommunicationStyle) -> None:
        self.condition: Condition = condition
        self.communication_style: CommunicationStyle = communication_style

    def generate(
        self, missions: Iterator[KtaneMissionSpec], pairings: Iterator[Pairing]
    ) -> Iterator[ExperimentSpec]:
        """Generate all possible experiments to be run from the given inputs."""
        for mission, pairing in itertools.product(missions, pairings):
            experiment = ExperimentSpec(
                mission_spec=mission,
                pairing=pairing,
                condition=self.condition,
                communication_style=self.communication_style,
            )
            yield experiment
