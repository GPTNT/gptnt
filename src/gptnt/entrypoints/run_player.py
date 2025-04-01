import asyncio

import hydra
from omegaconf import DictConfig

from gptnt.common.logger import configure_logging
from gptnt.common.paths import Paths
from gptnt.players.run import RunPlayerMixin

configure_logging()

paths = Paths()


@hydra.main(version_base="1.3", config_path=str(paths.configs), config_name="player.yaml")
def run_player(config: DictConfig) -> None:
    """Run the player.

    We use Hydra for this to allow us to easily switch between different configurations of players.
    """
    # Instantiate the player from the class
    player = hydra.utils.instantiate(config.player)
    assert isinstance(player, RunPlayerMixin)

    # Now run it in its loop
    asyncio.run(player.run())


if __name__ == "__main__":
    run_player()
