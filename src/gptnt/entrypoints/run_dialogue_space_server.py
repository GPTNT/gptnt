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
app = Typer()


async def run_dialogue_space_server(host: str, port: int) -> None:
    """Create and run the dialogue space server on the given host and port."""
    async with DialogueSpaceServer(server=WebsocketServer(host=host, port=port)) as dialogue_space:
        logger.info("Dialogue Space started", uri=f"ws://{host}:{port}")

        # Run until internal server is no longer running
        if dialogue_space.server.serving:
            await dialogue_space.server.serving

    logger.info("Dialogue Space stopped", uri=f"ws://{host}:{port}")


@app.command()
def start(host: str, port: int) -> None:
    """Runs the dialogue space server on the given uri."""
    logger.info("Starting server on host and port", host=host, port=port)
    asyncio.run(run_dialogue_space_server(host, port))


if __name__ == "__main__":
    app()
