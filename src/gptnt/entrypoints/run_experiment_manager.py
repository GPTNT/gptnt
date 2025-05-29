import asyncio

import logfire
from faststream.app import FastStream
from faststream.rabbit import RabbitBroker
from faststream.rabbit.opentelemetry import RabbitTelemetryMiddleware
from opentelemetry.sdk.trace.sampling import ParentBased
from structlog import get_logger

from gptnt.api.experiment_manager.experiment_manager import ExperimentManager
from gptnt.api.rabbit.exceptions import create_exc_middleware
from gptnt.common.instrumentation import HeartbeatFilterSampler
from gptnt.common.logger import configure_logging

_ = logfire.configure(
    service_name="experiment_manager",
    scrubbing=False,
    sampling=logfire.SamplingOptions(head=ParentBased(HeartbeatFilterSampler())),
)

configure_logging()
logger = get_logger()


async def run_experiment_manager() -> None:
    """Run an experiment manager."""
    broker = RabbitBroker(
        logger=None, middlewares=(RabbitTelemetryMiddleware(), create_exc_middleware())
    )
    experiment_manager = ExperimentManager(broker=broker)
    app = FastStream(broker, lifespan=experiment_manager.lifespan, logger=None)
    # Run the FastStream app until manual exit
    await app.run()


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    loop.run_until_complete(run_experiment_manager())
