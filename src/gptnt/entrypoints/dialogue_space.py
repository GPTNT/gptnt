import asyncio

from structlog import get_logger
from typer import Typer

from gptnt.common.logger import configure_logging
from gptnt.dialogue_space.server import DialogueSpaceServer
from gptnt.websocket_api.server import WebsocketServer

# Logging
configure_logging()
logger = get_logger()

# Typer CLI app to integrate nicely with docker
cli_app = Typer()


async def _start(host: str, port: int) -> None:
    """Async parts of start command: Starts the dialogue space on the given uri."""
    async with DialogueSpaceServer(server=WebsocketServer(host=host, port=port)) as dialogue_space:
        logger.info("Dialogue Space started", uri=f"ws://{host}:{port}")

        # Run until internal server is no longer running
        if dialogue_space.server.serving:
            await dialogue_space.server.serving

    logger.info("Dialogue Space stopped", uri=f"ws://{host}:{port}")


@cli_app.command()
def start(host: str, port: int) -> None:
    """Runs the dialogue space on the given uri."""
    logger.info(host=host)
    asyncio.run(_start(host, port))


if __name__ == "__main__":
    cli_app()
