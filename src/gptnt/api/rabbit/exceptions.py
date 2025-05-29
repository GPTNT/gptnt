import sys

from faststream import ExceptionMiddleware
from structlog import get_logger

_logger = get_logger()


def unhandled_exception_handler(exc: Exception) -> None:
    """Handle exceptions raised in the player from handlers."""
    _logger.exception("An error occurred in the player", exc_info=exc)
    sys.exit(1)


def create_exc_middleware() -> ExceptionMiddleware:
    """Create an exception middleware with the unhandled exception handler."""
    exc_middleware = ExceptionMiddleware()
    _ = exc_middleware.add_handler(Exception, publish=True)(unhandled_exception_handler)
    return exc_middleware
