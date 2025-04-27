import asyncio
from collections.abc import Callable
from typing import Any


async def healthcheck_interval() -> None:
    """Returns after the standard healthcheck interval has passed."""
    await asyncio.sleep(1)


async def busy_wait_interval() -> None:
    """Returns after the standard busy-wait interval has passed."""
    await asyncio.sleep(1)


async def until(get_value: Callable[[], Any], target: Any) -> None:
    """Await until a value (specified by passed getter) becomes the target."""
    while get_value() is not target:
        await busy_wait_interval()
