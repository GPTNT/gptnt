from collections.abc import Iterator
from typing import cast

import numpy as np
from pydantic import BaseModel, Field, NonNegativeInt

from gptnt.ktane.mission_spec import KtaneMissionSpec
from gptnt.ktane.state.modules import KtaneComponent


class MissionGeneratorConfig(BaseModel):
    """Config to generate missions for KTANE from."""

    time_limit: NonNegativeInt
    """Time limit for the game, in seconds."""

    allow_back_placement: bool
    """Are any modules allowed to be placed on the back?"""

    # Module sampling settings
    n_modules_min: NonNegativeInt = Field(ge=1)
    n_modules_max: NonNegativeInt = Field(ge=1)

    sample_from_modules: bool
    allow_repeat_module: bool

    min_optional_widgets: NonNegativeInt = Field(ge=1, default=1)
    max_optional_widgets: NonNegativeInt = Field(ge=1, default=5)

    excluded_modules: set[KtaneComponent] = Field(
        default_factory=lambda: {
            KtaneComponent.empty,
            KtaneComponent.timer,
            KtaneComponent.needy_vent_gas,
            KtaneComponent.needy_capacitor,
            KtaneComponent.needy_knob,
        }
    )

    @property
    def available_modules(self) -> list[KtaneComponent]:
        """Get a list of available modules."""
        all_modules = set(KtaneComponent)
        usable_modules = all_modules - self.excluded_modules
        return list(usable_modules)

    @property
    def expected_num_missions(self) -> int:
        """Get the expected number of missions."""
        if self.sample_from_modules:
            return 1
        return len(self.available_modules)


class MissionGenerator:
    """Generate missions for KTANE from the given config.

    Includes RNGs and seeds for reproducibility.
    """

    def __init__(
        self, *, config: MissionGeneratorConfig, num_seeds_per_mission: int = 3, seed: int = 42
    ) -> None:
        self.spec = config

        self._rng: np.random.Generator = np.random.default_rng(seed)
        self.seeds = cast(
            "list[int]",
            self._rng.integers(low=100, high=1000, size=num_seeds_per_mission).tolist(),
        )

    def generate(self) -> Iterator[KtaneMissionSpec]:
        """Generate mission specs based on the experiment condition.

        There are two main cases here: either we are generating a single mission spec for each seed
        by sampling from the available modules, OR we are going to be generating a mission spec for
        each possible module. The main "chooser" here is whether or not we want to sample from the
        middle of modules or not.

        This might have pain later but I don't really see it right now, so we do this.
        """
        for seed in self.seeds:
            self._reset_rng(seed)
            if self.spec.sample_from_modules:
                # Generate a single mission spec for each seed
                yield self._generate_mission(seed=seed, chosen_module=None)
            else:
                # Generate a mission spec for each module and seed combination
                for module in self._available_modules:
                    yield self._generate_mission(seed=seed, chosen_module=KtaneComponent(module))

    def _generate_mission(
        self, seed: int, *, chosen_module: KtaneComponent | None
    ) -> KtaneMissionSpec:
        """Generate one mission spec for a given condition."""
        n_components = self._rng.integers(
            low=self.spec.n_modules_min, high=self.spec.n_modules_max + 1
        ).item()

        # Either we use the chosen module OR we sample from all modules
        components = (
            [chosen_module for _ in range(n_components)]
            if chosen_module
            else self._sample_from_all_modules(n_components=n_components)
        )

        mission = KtaneMissionSpec.model_validate(
            {
                "seed": seed,
                "time_limit": self.spec.time_limit,
                "components": components,
                "optional_widgets": int(
                    self._rng.integers(
                        low=self.spec.min_optional_widgets, high=self.spec.max_optional_widgets + 1
                    )
                ),
                "force_modules_to_front": not self.spec.allow_back_placement,
            }
        )

        return mission

    def _sample_from_all_modules(self, n_components: int) -> list[KtaneComponent]:
        """Sample modules from all available modules."""
        sampled_modules = self._rng.choice(
            self._available_modules, size=n_components, replace=self.spec.allow_repeat_module
        )

        # If all sampled modules are the same, we resample and go again
        if len(set(sampled_modules)) <= 1:
            return self._sample_from_all_modules(n_components)

        return [KtaneComponent(module) for module in sampled_modules]

    def _reset_rng(self, seed: int) -> None:
        """Reset the random number generator with a specific seed."""
        self._rng = np.random.default_rng(seed)

    @property
    def _available_modules(self) -> list[str]:
        """Get a list of available modules."""
        return [component.value for component in self.spec.available_modules]
