from __future__ import annotations

import importlib
import inspect
from functools import partial, wraps
from typing import TYPE_CHECKING, Any, ClassVar, override

import anyio
import typer
from typer.core import TyperCommand, TyperGroup
from typer.rich_utils import rich_format_help

if TYPE_CHECKING:
    from collections.abc import Callable

    import click
    from click.core import Command
    from typer.models import CommandFunctionType


class LazyCommand(TyperCommand):
    """A Typer command whose module is only imported when the command is actually invoked.

    Stores the command name and help text pre-registration so that group `--help` pages render
    instantly without triggering any heavy imports.
    """

    def __init__(
        self,
        name: str,
        module: str,
        attr: str,
        help: str | None = None,  # noqa: A002
        rich_help_panel: str | None = None,
        typer_cls: type[typer.Typer] | None = None,
        **cmd_kwargs: Any,
    ) -> None:
        super().__init__(name=name, help=help)
        self._module = module
        self._attr = attr
        self._cmd_kwargs = cmd_kwargs
        self._typer_cls = typer_cls or typer.Typer
        self.rich_help_panel = rich_help_panel

        self.resolved: Command | None = None

    def __copy__(self) -> LazyCommand:
        """Create a shallow copy of this LazyCommand.

        It has the same import path and help text, but without sharing the resolved cache.
        """
        new = self.__class__.__new__(self.__class__)
        new.__dict__.update(self.__dict__)
        new.resolved = None  # don't share the resolved cache across copies
        return new

    @override
    def get_short_help_str(self, limit: int = 150) -> str:
        """Return pre-registered help text without importing the module."""
        text = (self.help or "").partition("\n")[0]
        return text[:limit]

    @override
    def make_context(
        self,
        info_name: str | None,
        args: list[str],
        parent: click.Context | None = None,
        **extra: Any,
    ) -> click.Context:
        return self._resolve().make_context(info_name, args, parent=parent, **extra)

    def _resolve(self) -> Command:
        """Lazily import the module and resolve the Click command to delegate to."""
        if self.resolved is not None:
            return self.resolved

        mod = importlib.import_module(self._module)
        resolved_obj = getattr(mod, self._attr)

        # If we pulled a typer command, then we can use it directly
        if isinstance(resolved_obj, TyperCommand):
            self.resolved = resolved_obj
        # If we pulled a typer app, then we delegate to its command resolution
        elif isinstance(resolved_obj, typer.Typer):
            self.resolved = typer.main.get_command(resolved_obj)
        else:
            # Bare function: wrap with the injected Typer class so that non-Typer functions are
            # handled correctly.
            temp_typer = self._typer_cls(add_completion=False)
            temp_typer.command(name=self.name, **self._cmd_kwargs)(resolved_obj)
            group = typer.main.get_command(temp_typer)

            # A single-command Typer produces a TyperGroup wrapping one TyperCommand.
            # Unwrap to the inner TyperCommand so Click doesn't expect a sub-command name
            # in the remaining args when this LazyCommand is dispatched.
            if isinstance(group, TyperGroup) and self.name and self.name in group.commands:
                self.resolved = group.commands[self.name]
            else:
                self.resolved = group

        return self.resolved


class LazyGroup(TyperGroup):
    """A TyperGroup that supports lazily-registered sub-commands with Rich help formatting.

    Eager sub-commands (added via `add_command`) are handled normally.
    Lazy sub-commands (added via `lazy_add`) are only imported when dispatched.

    Subclasses may set `default_typer_cls` to control which Typer class wraps bare functions
    during `LazyCommand._resolve`.
    """

    default_typer_cls: ClassVar[type[typer.Typer]] = typer.Typer

    def __init__(self, name: str | None = None, **attrs: Any) -> None:
        super().__init__(name=name, **attrs)
        self._lazy: dict[str, LazyCommand] = {}

    def lazy_add(
        self,
        name: str,
        module: str,
        attr: str,
        help: str | None = None,  # noqa: A002
        **cmd_kwargs: Any,
    ) -> None:
        """Register a sub-command by module path and attribute name without importing it."""
        self._lazy[name] = LazyCommand(
            name=name,
            module=module,
            attr=attr,
            help=help,
            typer_cls=type(self).default_typer_cls,
            **cmd_kwargs,
        )

    @override
    def list_commands(self, ctx: click.Context) -> list[str]:
        base = super().list_commands(ctx)
        lazy_names = sorted([name for name in self._lazy if name not in base])
        return base + lazy_names

    @override
    def get_command(self, ctx: click.Context, cmd_name: str) -> Command | None:
        if cmd_name in self._lazy:
            return self._lazy[cmd_name]
        return super().get_command(ctx, cmd_name)

    @override
    def format_help(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        rich_format_help(obj=self, ctx=ctx, markup_mode="rich")


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


class LazyAsyncGroup(LazyGroup):
    """LazyGroup that uses AsyncTyper to wrap bare async command functions.

    Setting `default_typer_cls = AsyncTyper` is stamped onto each `LazyCommand` created via
    `lazy_add`, so that `_resolve()` wraps the function with `anyio.run` — without `LazyGroup`
    or `LazyCommand` importing `AsyncTyper` themselves.
    """

    default_typer_cls = AsyncTyper
