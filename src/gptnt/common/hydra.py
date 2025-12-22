import sys

import structlog

logger = structlog.get_logger()


def get_hydra_overrides() -> list[str]:
    """Check and return any Hydra overrides passed as command line arguments."""
    hydra_overrides = sys.argv[1:] if len(sys.argv) > 1 else []
    if hydra_overrides:
        logger.debug(f"Hydra overrides: {hydra_overrides}")
    return hydra_overrides
