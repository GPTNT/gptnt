import types
import typing

from pydantic import BaseModel

from gptnt.records.models import ExperimentStepRecord


def _get_non_none_types(tp: typing.Any) -> list[typing.Any]:
    """Return the type arguments of tp, excluding NoneType.

    get_args returns type objects, so None appears as type(None) (the NoneType class) rather than
    the value None itself.
    """
    return [arg for arg in typing.get_args(tp) if arg is not type(None)]  # noqa: WPS516


def _resolve_type(tp: typing.Any) -> typing.Any:
    """Strip Annotated[X, ...] and X | None down to the core type."""
    if typing.get_origin(tp) is typing.Annotated:
        tp = typing.get_args(tp)[0]
    origin = typing.get_origin(tp)
    is_union = origin is typing.Union or (
        hasattr(types, "UnionType") and isinstance(tp, types.UnionType)
    )
    if is_union:
        non_none = _get_non_none_types(tp)
        if len(non_none) == 1:
            tp = non_none[0]
    return tp


def _expand_union(tp: typing.Any) -> list[typing.Any]:
    """Expand X | Y → [X, Y], dropping None."""
    origin = typing.get_origin(tp)
    is_union = origin is typing.Union or (
        hasattr(types, "UnionType") and isinstance(tp, types.UnionType)
    )
    if is_union:
        return _get_non_none_types(tp)
    return [tp]


def _get_list_inner(tp: typing.Any) -> typing.Any | None:
    """If tp is list[X], return X.

    Otherwise None.
    """
    if typing.get_origin(_resolve_type(tp)) is list:
        args = typing.get_args(_resolve_type(tp))
        return args[0] if args else typing.Any
    return None


def validate_path(path: str, model: type[BaseModel] = ExperimentStepRecord) -> None:  # noqa: WPS231
    """Validate the path against the model, raise if there are issues.

    Handles:
      - Nested BaseModel fields
      - list[X] with [] notation
      - Union types (checks all branches)
      - Annotated / Optional unwrapping
      - Non-model leaves (dict, primitives) — allowed through
    """
    segments = path.split(".")
    current_types: list[typing.Any] = [model]

    for segment in segments:
        is_list = segment.endswith("[]")
        field_name = segment.removesuffix("[]")
        next_types: list[typing.Any] = []

        for current_type in current_types:
            current = _resolve_type(current_type)

            if not (isinstance(current, type) and issubclass(current, BaseModel)):
                # Leaf / dict / primitive — can't introspect further, allow it
                next_types.append(current)
                continue

            if field_name not in current.model_fields:
                raise AttributeError(f"`{field_name}` is not a field of `{current.__name__}`")

            field_type = _resolve_type(current.model_fields[field_name].annotation)

            if is_list:
                inner = _get_list_inner(field_type)
                if inner is None:
                    raise AttributeError(
                        f"`{field_name}` is not a list field but path segment ends with `[]`"
                    )
                next_types.extend(_expand_union(_resolve_type(inner)))
            else:
                next_types.extend(_expand_union(field_type))

        if not next_types:
            raise AttributeError(f"`{field_name}` could not be resolved")

        current_types = next_types
