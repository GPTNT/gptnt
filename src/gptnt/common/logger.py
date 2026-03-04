import logging
from dataclasses import fields

import logfire
import structlog
from pydantic_ai import BinaryContent
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from structlog.typing import EventDict

from gptnt.common.run_once import run_once

logger = structlog.get_logger()


def binary_content_dataclasses_no_default_repr(
    self: BinaryContent, *, bytes_max_length: int = 100
) -> str:
    """Exclude fields with values equal to the field default, and truncate the data field.

    We are basically copying the code from pydantic_ai._utils.dataclasses_no_defaults_repr but
    truncating the data field to avoid large outputs.
    """
    kv_pairs = {
        field.name: getattr(self, field.name)
        for field in fields(self)
        if field.repr and getattr(self, field.name) != field.default
    }

    # Data will exist because it's required
    data = kv_pairs["data"]
    if len(data) > bytes_max_length:
        kv_pairs["data"] = f"{data[:bytes_max_length]!r} +{len(data) - bytes_max_length} bytes"

    kv_str = ", ".join(f"{key}={value!r}" for key, value in kv_pairs.items())  # noqa: WPS110
    return f"{self.__class__.__qualname__}({kv_str})"


def monkey_patch_binary_content_repr() -> None:
    """Monkey-patch the __repr__ method of pydantic_ai.BinaryContent to avoid large outputs.

    Rich's traceback handler displays local variables, including the full binary content of objects
    like BinaryContent. When exceptions occur with large binary payloads in scope, the traceback
    rendering can take >5 seconds, which blocks the task execution thread during render, therefore
    preventing heartbeat signals from being sent, leading to the service watcher in the EM to mark
    the service as dead.

    This monkey-patch changes the __repr__ method of BinaryContent to display a truncated version
    of the bytes instead of the full content.
    """
    BinaryContent.__repr__ = binary_content_dataclasses_no_default_repr
    # logger.debug("Monkey-patched BinaryContent.__repr__ to avoid large outputs in tracebacks")


def remove_duplicate_message(
    logger: logging.Logger,  # noqa: ARG001
    method_name: str,  # noqa: ARG001
    event_dict: EventDict,
) -> EventDict:
    """Remove 'message' key if it duplicates 'event'."""
    if (
        "message" in event_dict
        and "event" in event_dict
        and event_dict["message"] == event_dict["event"]
    ):
        event_dict.pop("message")
    return event_dict


@run_once
def configure_logging(root_log_level: int = logging.INFO, *, enable_logfire: bool = True) -> None:  # noqa: WPS213
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
        remove_duplicate_message,
        structlog.processors.StackInfoRenderer(),
    ]

    logfire_processor = [logfire.StructlogProcessor()] if enable_logfire else []

    # Configure structlog to use the standard library logging module, with the processors from
    # above
    structlog.configure(
        processors=[
            *shared_processors,
            *logfire_processor,
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
            structlog.dev.ConsoleRenderer(
                level_styles=log_level_colors,
                exception_formatter=structlog.dev.RichTracebackFormatter(show_locals=False),
            ),
        ],
    )

    root_logger = logging.getLogger()

    # Remove all handlers from root logger
    for existing_handler in root_logger.handlers[:]:
        root_logger.removeHandler(existing_handler)

    # Remove handlers from all existing loggers
    for logger_name in logging.root.manager.loggerDict:
        existing_logger = logging.getLogger(logger_name)
        existing_logger.handlers.clear()
        # Ensure they propagate to root
        existing_logger.propagate = True

    handler = logging.StreamHandler()  # noqa: WPS110
    # Use OUR `ProcessorFormatter` to format all `logging` entries.
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
    root_logger.setLevel(root_log_level)

    # Set httpx to WARNING to avoid too much noise
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.INFO)

    # Set faststream to warning to simplify logs
    logging.getLogger("faststream").setLevel(logging.WARNING)

    logging.getLogger("gptnt").setLevel(logging.DEBUG)

    monkey_patch_binary_content_repr()

    # def handle_exception(exc_type, exc_value, exc_traceback) -> None:
    #     """Log any uncaught exception instead of letting it be printed by Python.

    #     (but leave KeyboardInterrupt untouched to allow users to Ctrl+C to stop) See
    #     https://stackoverflow.com/a/16993115/3641865.
    #     """
    #     if issubclass(exc_type, KeyboardInterrupt):
    #         sys.__excepthook__(exc_type, exc_value, exc_traceback)
    #         return

    #     root_logger.exception("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

    # sys.excepthook = handle_exception


def create_faststream_logger(
    logger_name: str = "faststream", min_level: int = logging.WARNING
) -> structlog.BoundLogger:
    """Create a structlog logger for FastStream with the same configuration as the root logger."""
    return structlog.wrap_logger(
        structlog.get_logger(logger_name),
        wrapper_class=structlog.make_filtering_bound_logger(min_level),
    )


def create_progress(*, extra_fields: list[str] | None = None) -> Progress:
    """Create a Rich Progress instance with common columns and optional extra fields."""
    extra_fields = extra_fields or []
    extra_field_columns = [TextColumn(f"{{task.fields[{field}]}}") for field in extra_fields]
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        *extra_field_columns,
    )
