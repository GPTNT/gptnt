import types
from typing import Annotated, Any, Union, get_args, get_origin

# Covers both `Union[X, Y]` and the 3.10+ `X | Y` syntax.
UNION_ORIGINS: frozenset[Any] = frozenset(
    tp for tp in (Union, getattr(types, "UnionType", None)) if tp is not None
)


def is_union(tp: Any) -> bool:
    """Return True if tp is any form of Union (including X | Y)."""
    return get_origin(tp) in UNION_ORIGINS or (
        hasattr(types, "UnionType") and isinstance(tp, types.UnionType)
    )


def get_non_none_args(tp: Any) -> list[Any]:
    """Return the type arguments of a Union, excluding NoneType."""
    return [arg for arg in get_args(tp) if arg is not type(None)]  # noqa: WPS516


def expand_union(tp: Any) -> list[Any]:
    """Expand X | Y → [X, Y], dropping None.

    Wraps non-unions in a list.
    """
    if get_origin(tp) in UNION_ORIGINS or isinstance(tp, getattr(types, "UnionType", ())):
        return get_non_none_args(tp)
    return [tp]


def get_list_inner(tp: Any) -> Any | None:
    """If tp is list[X], return X.

    Caller is responsible for resolving Annotated/Optional first.
    """
    if get_origin(tp) is list:
        args = get_args(tp)
        return args[0] if args else Any
    return None


def resolve_type(tp: Any) -> Any:
    """Strip Annotated[X, ...] and X | None down to the core type."""
    if get_origin(tp) is Annotated:
        tp = get_args(tp)[0]
    if is_union(tp):
        non_none = get_non_none_args(tp)
        if len(non_none) == 1:
            tp = non_none[0]
    return tp


def extract_base_types(type_hint: type) -> set[type]:
    """Recursively extract all base types from a nested Union/Annotated structure."""
    args = get_args(type_hint)
    if is_union(type_hint):
        return {base for arg in args for base in extract_base_types(arg)}
    if get_origin(type_hint) is Annotated:
        return extract_base_types(args[0])
    return {type_hint}


def is_nullable(tp: Any) -> bool:
    """Return True if NoneType appears anywhere in the type's Union args."""
    return type(None) in extract_base_types(tp)  # noqa: WPS516
