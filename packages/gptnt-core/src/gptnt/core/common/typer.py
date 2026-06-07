from __future__ import annotations

import inspect
from functools import partial, wraps
from typing import TYPE_CHECKING, Any, override

import anyio
import typer

if TYPE_CHECKING:
    from collections.abc import Callable

    from typer.models import CommandFunctionType


class AsyncTyper(typer.Typer):
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

    def add_commands_from(self, other: typer.Typer, *, rich_help_panel: str | None = None) -> None:
        """Merge another Typer's commands in as top-level commands (flattened, not a sub-group).

        Unlike `add_typer`, this lifts each command onto this app directly, so they are invoked as
        `tool <command>` rather than `tool <group> <command>`. Pass `rich_help_panel` to keep them
        grouped together on the `--help` page.
        """
        for command_info in other.registered_commands:
            if rich_help_panel is not None:
                command_info.rich_help_panel = rich_help_panel
            self.registered_commands.append(command_info)
