import inspect
from collections.abc import Callable
from functools import partial, wraps
from typing import Any, override

import anyio
from typer import Typer
from typer.models import CommandFunctionType


class AsyncTyper(Typer):
    """Wrapper to run Typer with async automatically.

    Typer doesn't async out of the box, but someone did this and it works. I tried to clean up the
    types but I couldn't figure some of them out.

    Source: https://github.com/fastapi/typer/issues/950#issuecomment-2646361943
    """

    @staticmethod
    def maybe_run_async(  # noqa: WPS602
        decorator: Callable[[CommandFunctionType], CommandFunctionType], func: CommandFunctionType
    ) -> Any:
        """Run the function asynchronously if it is async."""
        if inspect.iscoroutinefunction(func):

            @wraps(func)
            def runner(*args: Any, **kwargs: Any) -> Any:  # noqa: WPS430
                return anyio.run(partial(func, *args, **kwargs))

            _ = decorator(runner)  # pyright: ignore[reportArgumentType]
        else:
            _ = decorator(func)
        return func

    @override
    def callback(
        self, *args: Any, **kwargs: Any
    ) -> Callable[[CommandFunctionType], CommandFunctionType]:
        decorator = super().callback(*args, **kwargs)
        return partial(self.maybe_run_async, decorator)

    @override
    def command(
        self, *args: Any, **kwargs: Any
    ) -> Callable[[CommandFunctionType], CommandFunctionType]:
        decorator = super().command(*args, **kwargs)
        return partial(self.maybe_run_async, decorator)
