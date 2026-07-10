from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, cast, get_args, get_origin, get_type_hints
from uuid import UUID

import duckdb
import msgpack
import zstandard as zstd
from caseconverter import snakecase
from pydantic import (
    BaseModel,
    GetCoreSchemaHandler,
    SerializationInfo,
    SerializerFunctionWrapHandler,
    model_serializer,
)
from pydantic_core import PydanticUndefined, core_schema, from_json, to_json, to_jsonable_python

from gptnt.common.types import UNION_ORIGINS, is_nullable

if TYPE_CHECKING:
    import pyarrow as pa

EXPORT_CONTEXT_MARKER = "db"


@dataclass(frozen=True)
class DuckDBType:
    """Annotated metadata marker to pin a field to a specific DuckDB type."""

    sql_type: str


@dataclass(frozen=True)
class AsBlob(DuckDBType):
    """Annotated marker that stores a field as a zstd+msgpack-compressed DuckDB BLOB.

    If you use this and then DuckDB the thing, we can easily use the context with dumping to store
    it as a compressed blob and return it back without needing all new logic.
    """

    sql_type: str = field(default="BLOB", init=False)

    @staticmethod
    def from_blob(v: bytes | bytearray) -> Any:  # noqa: WPS602
        """Decompress a stored BLOB back into a Python object."""
        return msgpack.unpackb(zstd.decompress(bytes(v)), raw=False)

    @staticmethod
    def to_blob(v: Any, *, context: Any = None) -> bytes:  # noqa: WPS602
        """Compress a Python object into the stored BLOB representation."""
        packed_bytes = cast(
            "bytes", msgpack.packb(to_jsonable_python(v, context=context), use_bin_type=True)
        )
        return zstd.compress(packed_bytes, level=19)

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        """Perform (de-)blob-ification when `context={"mode": "db"}`."""
        inner_schema = handler(source_type)

        def blob_validator(
            v: Any, next_validator: core_schema.ValidatorFunctionWrapHandler
        ) -> Any:
            if isinstance(v, (bytes, bytearray)):
                v = cls.from_blob(v)
            return next_validator(v)

        def blob_serializer(
            v: Any,
            next_serializer: core_schema.SerializerFunctionWrapHandler,
            info: core_schema.SerializationInfo,
        ) -> Any:
            if info.context and info.context.get("mode") == EXPORT_CONTEXT_MARKER:
                return cls.to_blob(v, context=info.context)
            return next_serializer(v)

        return core_schema.no_info_wrap_validator_function(
            blob_validator,
            inner_schema,
            serialization=core_schema.wrap_serializer_function_ser_schema(
                blob_serializer, schema=inner_schema, info_arg=True
            ),
        )


@dataclass(frozen=True)
class AsJSON(DuckDBType):
    """Annotated marker that stores a field as a DuckDB JSON column.

    Handles the round-trip: JSON strings returned by DuckDB are parsed back into Python objects
    before Pydantic validation runs.
    """

    sql_type: str = field(default="JSON", init=False)

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        """Parse JSON strings on the way in; serialise to JSON strings in DB export mode.

        Without the DB context, serialisation falls back to default Pydantic behaviour so that
        model_dump(mode="json") still produces plain Python objects for general use.
        """
        inner_schema = handler(source_type)

        def json_validator(
            v: Any, next_validator: core_schema.ValidatorFunctionWrapHandler
        ) -> Any:
            if isinstance(v, str):
                v = from_json(v)
            return next_validator(v)

        def json_serializer(
            v: Any, next_serializer: SerializerFunctionWrapHandler, info: SerializationInfo
        ) -> Any:
            if info.context and info.context.get("mode") == EXPORT_CONTEXT_MARKER:
                if v is None:
                    return None
                return to_json(v, context=info.context).decode()
            return next_serializer(v)

        return core_schema.no_info_wrap_validator_function(
            json_validator,
            inner_schema,
            serialization=core_schema.wrap_serializer_function_ser_schema(
                json_serializer, schema=inner_schema, info_arg=True
            ),
        )


@dataclass(frozen=True)
class AsVarchar(DuckDBType):
    """Annotated marker that stores a field as a DuckDB VARCHAR column.

    Serialises the Python value to `str(v)` when `context={"mode": "db"}`.

    On the way back in, the raw string is passed straight through to Pydantic's normal
    coercion/validation for the annotated type.
    """

    sql_type: str = field(default="VARCHAR", init=False)

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        """Stringify when `context={"mode": "db"}`."""
        inner_schema = handler(source_type)

        def varchar_validator(
            v: Any,
            next_validator: core_schema.ValidatorFunctionWrapHandler,
            info: core_schema.ValidationInfo,
        ) -> Any:
            # We might be using VARCHAR to json-serialize it so we need to try to get it back, but
            # not raise a problem if it doesnt work because another validate will handle it
            if info.context and info.context.get("mode") == EXPORT_CONTEXT_MARKER:
                with suppress(ValueError):
                    v = from_json(v)
            return next_validator(v)

        def varchar_serializer(
            v: Any,
            next_serializer: core_schema.SerializerFunctionWrapHandler,
            info: core_schema.SerializationInfo,
        ) -> Any:
            if info.context and info.context.get("mode") == EXPORT_CONTEXT_MARKER:
                return to_json(v, context=info.context).decode()
            return next_serializer(v)

        return core_schema.with_info_wrap_validator_function(
            varchar_validator,
            inner_schema,
            serialization=core_schema.wrap_serializer_function_ser_schema(
                varchar_serializer, schema=inner_schema, info_arg=True
            ),
        )


SCALAR_MAP: dict[type, str] = {  # noqa: WPS407
    str: "VARCHAR",
    int: "INTEGER",
    float: "DOUBLE",
    bool: "BOOLEAN",
    UUID: "UUID",
    Path: "VARCHAR",
    bytes: "BLOB",
}


def _as_duckdb_marker(meta: Any) -> DuckDBType | None:
    """Accept a DuckDBType instance OR the bare class (e.g. AsBlob without parens)."""
    if isinstance(meta, DuckDBType):
        return meta
    if isinstance(meta, type) and issubclass(meta, DuckDBType):
        sql_type = getattr(meta, "sql_type", None)
        if isinstance(sql_type, str):
            return DuckDBType(sql_type)
    return None


def _find_marker(annotation: type) -> DuckDBType | None:  # noqa: WPS231
    """Recursively find a DuckDBType marker anywhere in an annotation."""
    origin = get_origin(annotation)
    args = get_args(annotation)

    if origin is Annotated:
        for meta in args[1:]:
            if (marker := _as_duckdb_marker(meta)) is not None:
                return marker
        return _find_marker(args[0])

    if origin in UNION_ORIGINS:
        for arg in args:
            if arg is not type(None) and (marker := _find_marker(arg)):  # noqa: WPS516
                return marker

    return None


def _to_duckdb_type(annotation: type) -> str:
    origin = get_origin(annotation)
    args = get_args(annotation)

    if origin is Annotated:
        return _to_duckdb_type(args[0])

    if origin in UNION_ORIGINS:
        non_none = [arg for arg in args if arg is not type(None)]  # noqa: WPS516
        return _to_duckdb_type(non_none[0]) if len(non_none) == 1 else "VARCHAR"

    if origin is list:
        inner = _to_duckdb_type(args[0]) if args else "VARCHAR"
        return f"{inner}[]"

    if isinstance(annotation, type) and issubclass(annotation, Enum):  # pyright: ignore[reportUnnecessaryIsInstance]
        return "VARCHAR"

    return SCALAR_MAP.get(annotation, "VARCHAR")


def generate_duckdb_schema(model: type[DuckDBSchemaMixin]) -> str:  # noqa: WPS210, WPS231
    """Generate a CREATE TABLE statement from a DuckDBSchemaMixin subclass."""
    table_name = model.table_name()

    raw_hints = get_type_hints(model, include_extras=True)

    lines: list[str] = []
    for name, model_field in model.model_fields.items():
        raw = raw_hints.get(name, model_field.annotation)
        has_default = not model_field.is_required()

        override = _find_marker(raw)
        sql_type = override.sql_type if override else _to_duckdb_type(raw)
        nullable = has_default or is_nullable(raw)

        constraint = "" if nullable else " NOT NULL"
        lines.append(f"    {name} {sql_type}{constraint}")

    for name, cfield in model.model_computed_fields.items():
        raw = cfield.return_type

        if raw is PydanticUndefined:
            lines.append(f"    {name} VARCHAR")
            continue

        override = _find_marker(raw)
        sql_type = override.sql_type if override else _to_duckdb_type(raw)
        nullable = is_nullable(raw)

        constraint = "" if nullable else " NOT NULL"
        lines.append(f"    {name} {sql_type}{constraint}")

    return f"CREATE TABLE IF NOT EXISTS {table_name} (\n{',\n'.join(lines)}\n);"


def arrow_schema_for(model: type[DuckDBSchemaMixin]) -> pa.Schema:
    """Derive the parquet-writer arrow schema from the model's DuckDB schema.

    DuckDB is the single source of truth for column types: we create the table in an in-memory
    connection and read back the Arrow schema it produces, so the parquet columns line up
    name-for-name (and type-for-type) with the real table. `arrow_large_buffer_size` makes
    `BLOB → large_binary` (and strings → large_string), dodging the 32-bit offset limit on the big
    observation/message blobs.
    """
    with duckdb.connect(":memory:") as con:
        _ = con.execute("SET arrow_large_buffer_size = true")
        _ = con.execute(model.generate_duckdb_schema())
        return con.execute(f"SELECT * FROM {model.table_name()}").arrow().schema  # noqa: S608


class DuckDBSchemaMixin(BaseModel):
    """Mix into any BaseModel to get .create_table_sql()."""

    @classmethod
    def table_name(cls) -> str:
        """Return the DuckDB table name for this model."""
        if title := cls.model_config.get("title"):
            return title
        return snakecase(cls.__name__)

    @classmethod
    def generate_duckdb_schema(cls) -> str:
        """Generate a CREATE TABLE statement for this model."""
        return generate_duckdb_schema(cls)

    @classmethod
    def create_table(cls, conn: duckdb.DuckDBPyConnection) -> None:
        """Execute the schema against an open DuckDB connection."""
        _ = conn.execute(cls.generate_duckdb_schema())

    @model_serializer(mode="wrap")
    def db_serialize(
        self, handler: SerializerFunctionWrapHandler, info: SerializationInfo
    ) -> dict[str, Any]:
        """When context={'mode': 'db'}: AsBlob fields → compressed bytes, rest → JSON-compatible.

        The handler propagates context down to field-level serializers, so AsBlob fields naturally
        return bytes — no field-name hardcoding needed.
        """
        if info.context and info.context.get("mode") == EXPORT_CONTEXT_MARKER:
            raw = handler(self)  # AsBlob fields → bytes, others → Python objects
            return {
                k: v if isinstance(v, bytes) else to_jsonable_python(v) for k, v in raw.items()
            }
        return handler(self)
