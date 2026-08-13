from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from gptnt.common.paths import Paths


class ModuleFacts(BaseModel):
    """Intrinsic facts about one module.

    Every field defaults to the common case.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    needs_multiple_frames: bool = False
    """Whether the Defuser needs several observation frames for this module.

    True for a module whose answer is temporal, such as Simon Says' flash sequence.
    """


_DEFAULT_FACTS = ModuleFacts()


class ModuleRegistry(BaseModel):
    """Facts for the modules that deviate from the defaults, accessible using the `ModuleID`.

    These are facts/information that we need to know about a module to interact/play with it. For
    example, whether the module requires multiple observation frames when zoomed in. These are
    stored/loaded from the `configs/module_registry.yaml` file, and are accessible through the
    `ModuleID`. If a module is absent from the file, it is assumed to have the default facts.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    modules: dict[str, ModuleFacts] = Field(default_factory=dict)

    def facts(self, module_id: str) -> ModuleFacts:
        """Facts for a module, or the defaults when it is not recorded."""
        return self.modules.get(module_id, _DEFAULT_FACTS)

    def needs_multiple_frames(self, module_id: str) -> bool:
        """Whether the Defuser needs several observation frames of a module."""
        return self.facts(module_id).needs_multiple_frames


def _load_module_registry(path: Path) -> ModuleRegistry:
    """Load a registry from a specific YAML file."""
    return ModuleRegistry.model_validate(yaml.safe_load(path.read_text()))


@lru_cache(maxsize=1)
def module_registry() -> ModuleRegistry:
    """The registry shipped with GPTNT."""
    return _load_module_registry(Paths().module_registry)
