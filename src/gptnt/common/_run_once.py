from collections.abc import Callable
from functools import wraps


def run_once[**ParamT, ReturnT](fn: Callable[ParamT, ReturnT]) -> Callable[ParamT, ReturnT | None]:
    """Only let the function run once.

    Note: Since everything in Python is an object, we track whether the function has been run by
    manually setting an attribute on it. Bit of a hack but it works.

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
