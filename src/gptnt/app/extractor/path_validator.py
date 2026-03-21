import typing

from pydantic import BaseModel

from gptnt.common.types import expand_union, get_list_inner, resolve_type
from gptnt.records.models import ExperimentStepRecord


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
            current = resolve_type(current_type)

            if not (isinstance(current, type) and issubclass(current, BaseModel)):
                # Leaf / dict / primitive — can't introspect further, allow it
                next_types.append(current)
                continue

            if field_name not in current.model_fields:
                raise AttributeError(f"`{field_name}` is not a field of `{current.__name__}`")

            field_type = resolve_type(current.model_fields[field_name].annotation)

            if is_list:
                inner = get_list_inner(field_type)
                if inner is None:
                    raise AttributeError(
                        f"`{field_name}` is not a list field but path segment ends with `[]`"
                    )
                next_types.extend(expand_union(resolve_type(inner)))
            else:
                next_types.extend(expand_union(field_type))

        if not next_types:
            raise AttributeError(f"`{field_name}` could not be resolved")

        current_types = next_types
