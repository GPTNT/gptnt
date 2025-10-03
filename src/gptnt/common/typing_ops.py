import types
from typing import Annotated, Union, get_args, get_origin


def extract_base_types(type_hint: type) -> set[type]:
    """Recursively extract all base types from a nested Union/Annotated structure."""
    base_types = set()

    def _extract_recursive(current_type: type) -> None:  # noqa: WPS430
        origin = get_origin(current_type)

        # Handle Union types (both Union[A, B] and A | B syntax)
        if origin is Union or (hasattr(types, "UnionType") and origin is types.UnionType):
            # It's a Union, process each member
            for arg in get_args(current_type):
                _extract_recursive(arg)
        elif origin is Annotated:
            # It's Annotated, get the first argument (the actual type)
            actual_type = get_args(current_type)[0]
            _extract_recursive(actual_type)
        else:
            # It's a base type (or something we don't need to recurse into)
            base_types.add(current_type)

    _extract_recursive(type_hint)
    return base_types
