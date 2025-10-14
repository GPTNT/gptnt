import types
from typing import Annotated, Union, get_args, get_origin


def extract_base_types(type_hint: type) -> set[type]:
    """Recursively extract all base types from a nested Union/Annotated structure."""
    origin = get_origin(type_hint)
    args = get_args(type_hint)

    # Handle Union types (both Union[A, B] and A | B syntax)
    if origin in (Union, getattr(types, "UnionType", None)):
        return {base_type for arg in args for base_type in extract_base_types(arg)}

    # Handle Annotated types
    if origin is Annotated:
        return extract_base_types(args[0])

    # Base case: it's a base type
    return {type_hint}
