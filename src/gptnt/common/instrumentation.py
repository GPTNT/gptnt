import abc
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import structlog

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
        self.perform_instrumentation()

    @abc.abstractmethod
    def perform_instrumentation(self) -> None:
        """Perform instrumentation on the class."""
        raise NotImplementedError
