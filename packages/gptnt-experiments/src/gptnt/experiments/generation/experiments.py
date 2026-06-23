import itertools
from collections.abc import Iterator
from typing import Annotated

from pydantic import BaseModel, BeforeValidator

from gptnt.core.ktane.mission_spec import KtaneMissionSpec
from gptnt.core.specification import PlayerProtocol
from gptnt.experiments.generation.pairing import Pairing
from gptnt.experiments.spec import Condition, ExperimentSpec


class ExperimentGenerator(BaseModel):
    """Generate experiments from the given missions and pairings."""

    condition: Condition
    defuser_protocol: PlayerProtocol
    expert_protocol: Annotated[
        PlayerProtocol | None, BeforeValidator(lambda expert: expert or None)
    ]
    attempts_per_mission: int = 1

    def generate(
        self, missions: Iterator[KtaneMissionSpec], pairings: Iterator[Pairing]
    ) -> Iterator[ExperimentSpec]:
        """Generate all possible experiments to be run from the given inputs."""
        for mission, pairing in itertools.product(missions, pairings):
            if pairing.expert is not None and self.expert_protocol is None:
                raise ValueError(
                    "If the expert is set in the pairing, then `expert_protocol` must be set."
                )
            for attempt in range(1, self.attempts_per_mission + 1):
                experiment = ExperimentSpec(
                    mission_spec=mission,
                    condition=self.condition,
                    defuser_protocol=self.defuser_protocol,
                    defuser_name=pairing.defuser,
                    expert_protocol=self.expert_protocol,
                    expert_name=pairing.expert,
                    attempt=attempt,
                )
                yield experiment
