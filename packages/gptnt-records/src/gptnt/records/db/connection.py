from typing import Any, override

import duckdb
from streamlit.connections import BaseConnection

from gptnt.core.common.paths import Paths

paths = Paths()


class DuckDBConnection(BaseConnection[duckdb.DuckDBPyConnection]):
    """Streamlit connection for an embedded DuckDB file database."""

    def execute(self, query: str, params: list[Any] | None = None) -> duckdb.DuckDBPyConnection:
        """Execute a query against the underlying DuckDB connection."""
        return self._instance.cursor().execute(query, params or [])

    @override
    def _connect(self, **kwargs: Any) -> duckdb.DuckDBPyConnection:
        database = kwargs.get("database") or self._secrets.get("database")
        if not database:
            kwargs["database"] = paths.experiments_db

        return duckdb.connect(**kwargs)
