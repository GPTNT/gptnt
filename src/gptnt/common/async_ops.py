import asyncio
from collections.abc import Callable, Coroutine
from typing import Any


def healthcheck_interval() -> Coroutine[Any, Any, None]:
    """Returns after the standard healthcheck interval has passed."""
    return asyncio.sleep(1)


def busy_wait_interval() -> Coroutine[Any, Any, None]:
    """Returns after the standard busy-wait interval has passed."""
    return asyncio.sleep(1)


async def until(get_value: Callable[[], Any], target: Any) -> None:
    """Await until a value (specified by passed getter) becomes the target."""
    while get_value() is not target:
        await busy_wait_interval()
