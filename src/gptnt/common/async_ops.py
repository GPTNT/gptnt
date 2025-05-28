import asyncio
import inspect
from collections.abc import Callable, Coroutine
from threading import Thread
from typing import Any


def healthcheck_interval() -> Coroutine[Any, Any, None]:
    """Returns after the standard healthcheck interval has passed."""
    return asyncio.sleep(1.0)


def busy_wait_interval() -> Coroutine[Any, Any, None]:
    """Returns after the standard busy-wait interval has passed."""
    return asyncio.sleep(1.0)


async def until[TargetT](
    get_value: Callable[[], TargetT] | Callable[[], Coroutine[TargetT, Any, Any]],  # noqa: WPS221
    target: TargetT,
) -> None:
    """Await until a value (specified by passed getter) becomes the target."""
    # This now works with partial coroutinefunctions and functions returning awaitables which
    # are not explicitly marked as coroutinefunctions
    while (await v if inspect.isawaitable(v := get_value()) else v) is not target:  # noqa: WPS509, WPS111
        await busy_wait_interval()


async def run_in_separate_thread(to_thread_func: Callable[[], Any]) -> None:
    """Run a function in a separate thread and wait for it to finish.

    Do not expect a return.
    """
    worker_thread = Thread(target=to_thread_func)
    worker_thread.start()

    while worker_thread.is_alive():
        await busy_wait_interval()

    worker_thread.join()
