from collections.abc import Callable
from functools import wraps
from typing import override


class RunOnceError(RuntimeError):
    """Custom error for run_once decorator."""

    default_message = "This function has already been run and cannot be run again."

    def __init__(self, message: str | None = None) -> None:
        message = message or self.default_message
        super().__init__(message)
        self.message = message

    @override
    def __str__(self) -> str:
        return f"RunOnceError: {self.message}"


def run_once[**ParamT, ReturnT](fn: Callable[ParamT, ReturnT]) -> Callable[ParamT, ReturnT | None]:
    """Only let the function run once.

    Note: We manually set an attribute on the function to track if it has been run since everything
    in Python is an object. Bit of a hack but it works.

    Inspired by: https://cosmiccoding.com.au/tutorials/handy_python_decorators/
    """

    @wraps(fn)
    def wrapper(*args: ParamT.args, **kwargs: ParamT.kwargs) -> ReturnT | None:
        # Raise exception if already run
        if getattr(wrapper, "has_run", True):
            raise RuntimeError(
                f"{fn.__name__} has already been run. It cannot be run again."
            ) from None

        wrapper.has_run = True  # pyright: ignore[reportAttributeAccessIssue]
        return fn(*args, **kwargs)

    wrapper.has_run = False  # pyright: ignore[reportAttributeAccessIssue]
    return wrapper
