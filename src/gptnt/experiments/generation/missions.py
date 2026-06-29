from collections.abc import Iterator
from pathlib import Path
from typing import cast

import numpy as np
from pydantic import BaseModel, Field, NonNegativeInt

from gptnt.ktane.mission_spec import KtaneMissionSpec
from gptnt.ktane.state.modules import KtaneComponent
from gptnt.ktane.time_limits import get_time_limit_for_mission


class MissionGeneratorConfig(BaseModel):
    """Config to generate missions for KTANE from."""

    time_limit: NonNegativeInt | None
    """Time limit for the game, in seconds.

    If None, the time limit will be calculated based on the modules.
    """

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
        return sorted(usable_modules, key=lambda component: component.value)

    @property
    def expected_num_missions(self) -> int:
        """Get the expected number of missions."""
        if self.sample_from_modules:
            return 1
        return len(self.available_modules)


def load_missions(missions_path: Path) -> list[KtaneMissionSpec]:
    """Load every materialised mission spec from a set directory, sorted by file name."""
    mission_files = sorted(missions_path.glob("*.json"))
    if not mission_files:
        raise FileNotFoundError(f"No mission specs found in {missions_path}")
    return [KtaneMissionSpec.model_validate_json(path.read_text()) for path in mission_files]


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
        """Generate fresh mission specs from the configured seeds.

        This is the authoring path that materialises a mission set. The run path never generates.
        It loads the materialised files with `load_missions`.
        """
        for seed in self.seeds:
            self._reset_rng(seed)
            yield from self._generate_for_seed(seed)

    def _generate_for_seed(self, seed: int) -> Iterator[KtaneMissionSpec]:
        """Generate mission specs for a specific seed."""
        if self.spec.sample_from_modules:
            yield self._generate_mission(seed=seed, chosen_module=None)
        else:
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

        time_limit = (
            get_time_limit_for_mission(
                components, allow_back_placement=self.spec.allow_back_placement
            )
            if self.spec.time_limit is None
            else self.spec.time_limit
        )

        mission = KtaneMissionSpec.model_validate(
            {
                "seed": seed,
                "time_limit": time_limit,
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
