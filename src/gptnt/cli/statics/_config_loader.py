from collections.abc import Callable
from dataclasses import dataclass

import hydra
from omegaconf import DictConfig
from pydantic_ai import Agent

from gptnt.cli.models import PlayerSpec
from gptnt.common.paths import Paths
from gptnt.processors.image_resizer import ImageResizer
from gptnt.specification import PlayerCapabilities, PlayerRole

paths = Paths()


@dataclass(kw_only=True)
class ConfigLoader:
    """Load and instantiate player config components for a given model + role."""

    player_spec: PlayerSpec
    role: PlayerRole

    @property
    def config(self) -> DictConfig:
        """Compose the Hydra player config for this model."""
        overrides = [f"model={self.player_spec.model_name}"]
        if self.player_spec.provider is not None:
            overrides.append(f"model/provider={self.player_spec.provider}")
        with hydra.initialize_config_dir(version_base="1.3", config_dir=str(paths.configs)):
            return hydra.compose(config_name="player", overrides=overrides)

    @property
    def capabilities(self) -> PlayerCapabilities:
        """Instantiate PlayerCapabilities from config."""
        return hydra.utils.instantiate(self.config.player.capabilities)

    @property
    def image_resizer(self) -> ImageResizer:
        """Instantiate the image resizer, swapping dimensions by role."""
        capabilities = self.capabilities
        match self.role:
            case "defuser":
                target_width = capabilities.image_dimensions.long_side
                target_height = capabilities.image_dimensions.short_side
            case "expert":
                target_width = capabilities.image_dimensions.short_side
                target_height = capabilities.image_dimensions.long_side
        return hydra.utils.instantiate(
            self.config.player.observation_handler.image_resizer,
            target_width=target_width,
            target_height=target_height,
        )

    @property
    def agent_fn(self) -> Callable[..., Agent]:
        """Return a partial for constructing the PydanticAI agent."""
        return hydra.utils.instantiate(self.config.player.action_predictor.agent, _partial_=True)
