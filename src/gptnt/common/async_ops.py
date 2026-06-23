import os
from collections.abc import AsyncIterator, Callable
from typing import Self, override

import anyio


async def periodic(interval: float) -> AsyncIterator[tuple[float, float | None]]:
    """Yield periodically with elapsed time."""
    start_time = anyio.current_time()
    last_time = start_time
    while True:  # noqa: WPS457
        await anyio.sleep(interval)
        current_time = anyio.current_time()
        elapsed = current_time - start_time
        delta = current_time - last_time
        last_time = current_time
        yield elapsed, delta


class Event(anyio.Event):
    """Wrapped event class to help with testing.

    `wait` is troublesome to test with for some reason, so have an alternative that we use when we
    are testing, determined by the `TESTING` environment variable.
    """

    @override
    def __new__(cls) -> Self:
        """Just inherit from the super for the __new__.

        This is needed to appease the typechecker for some reason. I don't get it.
        """
        return super().__new__(cls)  # pyright: ignore[reportReturnType]

    @override
    async def wait(self) -> None:
        """Wait for the event to be set."""
        if self._is_testing:
            async for _ in periodic(1):
                if self.is_set():
                    return None

        return await super().wait()

    @property
    def _is_testing(self) -> bool:
        """Determine if we are in a testing environment."""
        return os.environ.get("TESTING", "0") == "1"


class AsyncValue[T]:  # noqa: WPS111
    """Simple AsyncValue implementation for AnyIO, inspired by trio."""

    def __init__(self, initial_value: T) -> None:
        self._value = initial_value  # noqa: WPS110
        self._event = Event()

    @property
    def value(self) -> T:  # noqa: WPS110
        """Get the current value."""
        return self._value

    @value.setter
    def value(self, new_value: T) -> None:  # noqa: WPS110
        self._value = new_value  # noqa: WPS110
        self._event.set()
        # Reset for next change
        self._event = Event()

    async def wait_value(self, target: T | Callable[[T], bool]) -> T:
        """Wait for a specific value or condition."""
        while True:
            if callable(target):
                if target(self._value):
                    return self._value
            elif self._value == target:
                return self._value
            await self._event.wait()

    async def wait_transition(self) -> tuple[T, T]:
        """Wait for any value change."""
        old_value = self._value
        await self._event.wait()
        return self._value, old_value
