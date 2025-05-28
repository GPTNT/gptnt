import abc
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, override

import logfire
import structlog
from opentelemetry.context import Context
from opentelemetry.sdk.trace.sampling import ALWAYS_OFF, ALWAYS_ON, Sampler, SamplingResult
from opentelemetry.trace import Link, SpanKind
from opentelemetry.trace.span import TraceState
from opentelemetry.util.types import Attributes

if TYPE_CHECKING:
    from collections.abc import Callable

logger = structlog.get_logger()


class PostInitMeta(abc.ABCMeta):
    """Metaclass that automatically calls a `post_init` method, if it exists.

    This pattern defines a post-initialisation logic in a clean and reusable way,
    similar to `__post_init__` in dataclasses, but for any class.

    Inherits from `abc.ABCMeta` so you can also declare abstract methods.
    """

    def __new__(
        mcs: type[type], name: str, bases: tuple[type, ...], namespace: dict[str, Any]
    ) -> type:
        """Create a new class with the metaclass."""
        orig_init: Callable[..., None] | None = namespace.get("__init__")

        def __init__(self: Any, *args: Any, **kwargs: Any) -> None:  # noqa: N807, WPS430
            """Replacement __init__ that calls the original __init__ and then self.post_init()."""
            # If the original __init__ exists, call it with the same arguments
            if orig_init is not None:  # noqa: WPS504
                orig_init(self, *args, **kwargs)

            # Otherwise, call the superclass __init__ method instead
            else:
                super(cls, self).__init__(*args, **kwargs)  # noqa: WPS608

            # Automatically call post_init if it exists
            if hasattr(self, "post_init") and callable(self.post_init):
                _ = self.post_init()

        # Replace the original __init__ with the new one. Bit of a hack, but it works.
        namespace["__init__"] = __init__

        # Create the class using the modified namespace
        cls = super().__new__(  # noqa: WPS117
            mcs,
            name,  # pyright: ignore[reportCallIssue]
            bases,
            namespace,
        )
        return cls


class InstrumentationMixin(abc.ABC, metaclass=PostInitMeta):
    """Simplify instrumentation of clients within a class.

    Subclasses should implement the `perform_instrumentation` method to define the specific
    instrumentation logic.
    """

    def post_init(self) -> None:
        """Post-initialisation method that performs instrumentation."""
        if not logfire.DEFAULT_LOGFIRE_INSTANCE.config.send_to_logfire:
            logger.debug("Logfire is not enabled, skipping instrumentation.")
            return
        self.perform_instrumentation()

    @abc.abstractmethod
    def perform_instrumentation(self) -> None:
        """Perform instrumentation on the class."""
        raise NotImplementedError


@dataclass
class InstrumentationDataclassMixin(abc.ABC):
    """Simplify instrumentation of clients within a dataclass.

    Subclasses should implement the `perform_instrumentation` method to define the specific
    """

    def __post_init__(self) -> None:
        """Post-initialisation method that performs instrumentation."""
        if not logfire.DEFAULT_LOGFIRE_INSTANCE.config.send_to_logfire:
            logger.debug("Logfire is not enabled, skipping instrumentation.")
            return
        self.perform_instrumentation()

    @abc.abstractmethod
    def perform_instrumentation(self) -> None:
        """Perform instrumentation on the class."""
        raise NotImplementedError


class HeartbeatFilterSampler(Sampler):
    """Custom sampler that filters out spans with 'heartbeat' in their name."""

    @override
    def should_sample(
        self,
        parent_context: Context | None,
        trace_id: int,
        name: str,
        kind: SpanKind | None = None,
        attributes: Attributes = None,
        links: Sequence[Link] | None = None,
        trace_state: TraceState | None = None,
    ) -> SamplingResult:
        # Check if 'heartbeat' is anywhere in the span name (case-insensitive)
        sampler = ALWAYS_OFF if "experiment.heartbeat" in name.lower() else ALWAYS_ON

        if (
            "heartbeat" in name.lower()
            and attributes is not None
            and attributes.get("messaging.system", None) == "rabbitmq"
        ):
            # If the span is a RabbitMQ heartbeat, use ALWAYS_OFF
            sampler = ALWAYS_OFF

        return sampler.should_sample(
            parent_context, trace_id, name, kind, attributes, links, trace_state
        )

    @override
    def get_description(self) -> str:
        return "HeartbeatFilterSampler"
