import structlog


def configure_logging() -> None:
    """Configure structlog for structured logging."""
    structlog.stdlib.recreate_defaults()
