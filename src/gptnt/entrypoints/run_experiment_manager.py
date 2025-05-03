from functools import partial
from typing import Annotated

import logfire
import structlog
import typer
from fastapi import FastAPI

from gptnt.api.experiment_manager_routes import lifespan, router
from gptnt.common.logger import configure_logging

_ = logfire.configure(service_name="experiment-manager", scrubbing=False)
logfire.instrument_system_metrics(
    config={
        "process.cpu.utilization": None,
        "system.cpu.simple_utilization": None,
        "process.memory.usage": None,
        "process.memory.virtual": None,
        "process.open_file_descriptor.count": None,
        "process.thread.count": None,
        "system.disk.io": ["read", "write"],
        "system.memory.utilization": ["available"],
        "system.disk.operations": ["read", "write"],
        "system.network.errors": ["transmit", "receive"],
    }
)
configure_logging()

cli = typer.Typer(no_args_is_help=True)

_logger = structlog.get_logger()


def _run_with_uvicorn(app: FastAPI) -> None:
    import uvicorn

    uvicorn.run(app, host="localhost", port=8099, log_level="warning")  # noqa: WPS432
    _logger.info("App closed")


@cli.command()
def run(
    *, is_prod: Annotated[bool, typer.Option("--prod", help="Run in production mode")] = False
) -> None:
    """Runs the room forever, gracefully exiting (without zombies!) on Ctrl+C."""
    app = FastAPI(lifespan=partial(lifespan, filter_with_wandb=is_prod))
    app.include_router(router)
    _ = logfire.instrument_fastapi(app, excluded_urls=["/health"])

    _run_with_uvicorn(app)


if __name__ == "__main__":
    cli()
