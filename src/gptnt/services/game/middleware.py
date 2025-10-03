import structlog
from fastapi import Request, Response
from starlette.middleware.base import RequestResponseEndpoint

from gptnt.services.game.lifespan import get_game_state_monitor
from gptnt.services.timeouts import ServiceTimeouts

logger = structlog.get_logger()
service_timeouts = ServiceTimeouts()


async def add_state_headers_to_response(
    request: Request, call_next: RequestResponseEndpoint
) -> Response:
    """Add state headers to the response."""
    state_monitor = await get_game_state_monitor(request)
    response = await call_next(request)
    response.headers["X-State-History"] = ",".join(state.value for state in state_monitor.history)
    response.headers["X-Light-On-Event"] = str(state_monitor.first_lights_on.is_set())
    return response
