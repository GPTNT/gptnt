import asyncio
from collections.abc import Callable, Coroutine
from threading import Thread
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


async def run_in_separate_thread(to_thread_func: Callable[[], None]) -> None:
    """Run a function in a separate thread and wait for it to finish."""
    worker_thread = Thread(target=to_thread_func)
    worker_thread.start()

    while worker_thread.is_alive():
        await busy_wait_interval()

    worker_thread.join()
