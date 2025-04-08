import logging

import structlog

from gptnt.common.run_once import run_once


@run_once
def configure_logging(root_log_level: int = logging.INFO) -> None:
    """Configure structlog for structured logging.

    To ensure all the logs are piped together and look the same, everything is put through
    structlog. I followed this guide:
    https://www.structlog.org/en/stable/standard-library.html#rendering-using-structlog-based-formatters-within-logging
    """
    shared_processors = [
        # Add a timestamp
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
        # Add the name of the logger
        structlog.stdlib.add_logger_name,
        # Add the log level
        structlog.stdlib.add_log_level,
        # Include any extras in the log dict
        structlog.stdlib.ExtraAdder(),
    ]

    # Configure structlog to use the standard library logging module, with the processors from
    # above
    structlog.configure(
        processors=[*shared_processors, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        # These run ONLY on `logging` entries that do NOT originate within
        # structlog.
        foreign_pre_chain=shared_processors,
        # These run on ALL entries after the pre_chain is done.
        processors=[
            # Remove _record & _from_structlog.
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.dev.ConsoleRenderer(),
        ],
    )

    handler = logging.StreamHandler()  # noqa: WPS110
    # Use OUR `ProcessorFormatter` to format all `logging` entries.
    handler.setFormatter(formatter)
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(root_log_level)
