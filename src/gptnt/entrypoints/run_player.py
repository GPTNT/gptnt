from functools import partial

import hydra
import logfire
import uvicorn
from fastapi import FastAPI
from omegaconf import DictConfig
from structlog import get_logger

from gptnt.api.experiment_manager_client import ExperimentManagerClient
from gptnt.api.player_lifespan import player_lifespan
from gptnt.api.player_routes import player_router
from gptnt.common.hosting import get_available_port
from gptnt.common.logger import configure_logging
from gptnt.common.paths import Paths
from gptnt.experiments.structures import PlayerAPIInfo
from gptnt.players.base_player import BasePlayer

# TODO: We need to contextualise the service with the metadata when we run things
_ = logfire.configure(service_name="player")
configure_logging()

_logger = get_logger()

paths = Paths()


@hydra.main(version_base="1.3", config_path=str(paths.configs), config_name="player.yaml")
def run_player(config: DictConfig) -> None:  # noqa: WPS210
    """Run the player.

    We use Hydra for this to allow us to easily switch between different configurations of players.
    """
    # Instantiate the player from the class
    player = hydra.utils.instantiate(config.player)
    assert isinstance(player, BasePlayer)

    experiment_manager_client = hydra.utils.instantiate(config.experiment_manager_client)
    assert isinstance(experiment_manager_client, ExperimentManagerClient)

    api_host = "localhost"
    api_port = get_available_port()

    api_info = PlayerAPIInfo(
        fastapi_url=f"http://{api_host}:{api_port}",
        player_type=player.player_type,
        player_role=player.player_role,
    )
    app = FastAPI(
        lifespan=partial(
            player_lifespan,
            player=player,
            experiment_manager_client=experiment_manager_client,
            api_info=api_info,
        )
    )
    # Include the router with the endpoints.
    app.include_router(player_router)
    _ = logfire.instrument_fastapi(app, excluded_urls=["/health"])
    # Start the server.
    uvicorn.run(app, host=api_host, port=api_port, log_level="warning")


if __name__ == "__main__":
    run_player()
