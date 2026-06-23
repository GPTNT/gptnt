from gptnt.core.ktane.state.modules import KtaneComponent
from gptnt.experiments.generation.missions import MissionGeneratorConfig


class MissionGeneratorConfigCases:
    def case_single_module(self) -> MissionGeneratorConfig:
        return MissionGeneratorConfig(
            time_limit=60,
            allow_back_placement=False,
            n_modules_min=1,
            n_modules_max=1,
            sample_from_modules=False,
            allow_repeat_module=False,
            min_optional_widgets=1,
            max_optional_widgets=5,
        )

    def case_multiple_modules(self) -> MissionGeneratorConfig:
        return MissionGeneratorConfig(
            time_limit=60,
            allow_back_placement=True,
            n_modules_min=2,
            n_modules_max=5,
            sample_from_modules=True,
            allow_repeat_module=False,
            min_optional_widgets=1,
            max_optional_widgets=5,
        )

    def case_repeated_modules(self) -> MissionGeneratorConfig:
        return MissionGeneratorConfig(
            time_limit=60,
            allow_back_placement=True,
            n_modules_min=3,
            n_modules_max=5,
            sample_from_modules=True,
            allow_repeat_module=True,
            min_optional_widgets=1,
            max_optional_widgets=5,
            # Force there to be repeated modules
            excluded_modules=set(KtaneComponent)
            - {KtaneComponent.big_button, KtaneComponent.keypad},
        )
