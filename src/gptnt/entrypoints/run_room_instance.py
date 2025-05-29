import asyncio
from uuid import uuid4

import logfire
from faststream.app import FastStream
from faststream.rabbit import RabbitBroker
from faststream.rabbit.opentelemetry import RabbitTelemetryMiddleware
from opentelemetry.sdk.trace.sampling import ParentBased
from structlog import get_logger

from gptnt.api.rabbit.exceptions import create_exc_middleware
from gptnt.api.room_manager.room_instance import RoomInstance
from gptnt.common.instrumentation import HeartbeatFilterSampler
from gptnt.common.logger import configure_logging

_ = logfire.configure(
    service_name="room",
    scrubbing=False,
    sampling=logfire.SamplingOptions(head=ParentBased(HeartbeatFilterSampler())),
)


configure_logging()
logger = get_logger()


async def run_room_instance() -> None:
    """Run a room instance."""
    broker = RabbitBroker(
        logger=None, middlewares=(RabbitTelemetryMiddleware(), create_exc_middleware())
    )
    game_manager = RoomInstance(broker=broker, uuid=uuid4())
    app = FastStream(broker, lifespan=game_manager.lifespan, logger=None)

    # Run the FastStream app until manual exit
    await app.run()


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    loop.run_until_complete(run_room_instance())
