"""Resolve the player identity carried from configuration into benchmark outputs."""

from dataclasses import dataclass
from typing import Literal

from hydra.errors import InstantiationException
from hydra.utils import instantiate
from omegaconf import DictConfig
from omegaconf.errors import OmegaConfBaseException

from gptnt.players.specification import PlayerCapabilities, PlayerIdentity

type PlayerConfigComponent = Literal["capabilities", "identity"]


class PlayerConfigResolutionError(ValueError):
    """A composed player component could not be instantiated."""

    def __init__(
        self,
        component: PlayerConfigComponent,
        error: Exception,
        *,
        capabilities: PlayerCapabilities | None = None,
    ) -> None:
        self.component: PlayerConfigComponent = component
        self.capabilities = capabilities
        super().__init__(str(error))


@dataclass(frozen=True, kw_only=True)
class ResolvedPlayerConfig:
    """Composed config with the capabilities and presentation metadata it resolves to."""

    config: DictConfig
    capabilities: PlayerCapabilities
    identity: PlayerIdentity


def resolve_player_config(config: DictConfig) -> ResolvedPlayerConfig:
    """Instantiate the one player identity used by runtime and evaluation consumers."""
    try:
        capabilities = instantiate(config.player.capabilities)
    except (InstantiationException, OmegaConfBaseException) as error:
        raise PlayerConfigResolutionError("capabilities", error) from error

    try:
        identity = instantiate(config.player.identity)
    except (InstantiationException, OmegaConfBaseException) as error:
        raise PlayerConfigResolutionError("identity", error, capabilities=capabilities) from error

    return ResolvedPlayerConfig(config=config, capabilities=capabilities, identity=identity)
