import logging

import logfire
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
        structlog.contextvars.merge_contextvars,
        # Add a timestamp
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
        # Add the name of the logger
        structlog.stdlib.add_logger_name,
        # Add the log level
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        # structlog.processors.CallsiteParameterAdder(
        #     [CallsiteParameter.PROCESS, CallsiteParameter.FUNC_NAME, CallsiteParameter.LINENO]
        # ),
        # Include any extras in the log dict
        structlog.stdlib.ExtraAdder(),
        structlog.processors.StackInfoRenderer(),
    ]

    # Configure structlog to use the standard library logging module, with the processors from
    # above
    structlog.configure(
        processors=[
            *shared_processors,
            logfire.StructlogProcessor(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Set debug to be a different color
    log_level_colors = structlog.dev.ConsoleRenderer.get_default_level_styles()
    log_level_colors["debug"] = "\x1b[34m"

    formatter = structlog.stdlib.ProcessorFormatter(
        # These run ONLY on `logging` entries that do NOT originate within
        # structlog.
        foreign_pre_chain=shared_processors,
        # These run on ALL entries after the pre_chain is done.
        processors=[
            # Remove _record & _from_structlog.
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.dev.ConsoleRenderer(level_styles=log_level_colors),
        ],
    )

    handler = logging.StreamHandler()  # noqa: WPS110
    # Use OUR `ProcessorFormatter` to format all `logging` entries.
    handler.setFormatter(formatter)
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(root_log_level)

    # Set httpx to WARNING to avoid too much noise
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.INFO)

    logging.getLogger("gptnt").setLevel(logging.DEBUG)

    # def handle_exception(exc_type, exc_value, exc_traceback) -> None:
    #     """Log any uncaught exception instead of letting it be printed by Python.

    #     (but leave KeyboardInterrupt untouched to allow users to Ctrl+C to stop)
    #     See https://stackoverflow.com/a/16993115/3641865.
    #     """
    #     if issubclass(exc_type, KeyboardInterrupt):
    #         sys.__excepthook__(exc_type, exc_value, exc_traceback)
    #         return

    #     root_logger.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

    # sys.excepthook = handle_exception
