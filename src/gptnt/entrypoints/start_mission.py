from typing import Annotated

import httpx
import typer
from structlog import get_logger

from gptnt.common.logger import configure_logging
from gptnt.entrypoints._async_typer import AsyncTyper
from gptnt.ktane.client import KtaneClient
from gptnt.ktane.mission_spec import KtaneMissionSpec

configure_logging()
logger = get_logger()
app = AsyncTyper()


@app.command()
async def start_mission(
    url: str,
    *,
    seed: Annotated[int, typer.Option()],
    time_limit: Annotated[int, typer.Option()],
    num_strikes_allowed: Annotated[int, typer.Option()],
    components: Annotated[str, typer.Option()],
    optional_widgets: Annotated[int, typer.Option()] = 0,
) -> None:
    """Simple entrypoint to start a mission in the KTANE through the mod."""
    mission_spec = KtaneMissionSpec.model_validate(
        {
            "seed": seed,
            "time_limit": time_limit,
            "num_strikes_allowed": num_strikes_allowed,
            "components": components,
            "optional_widgets": optional_widgets,
        }
    )

    client = KtaneClient(client=httpx.AsyncClient(base_url=url))

    async with client:
        if not await client.healthcheck():
            raise typer.Exit(1)

        if not await client.start_mission(mission_spec):
            logger.error("Failed to start mission")
            raise typer.Exit(1)
        logger.info("Mission started successfully")


if __name__ == "__main__":
    app()
