"""DuckDB connection helpers for the Streamlit app.

Connection strategy
-------------------
The DuckDB engine is managed via :class:`DuckDBConnection`, a Streamlit
``BaseConnection`` subclass.  ``st.connection`` caches it globally via
``st.cache_resource`` — the Streamlit-idiomatic equivalent of the previous
``@cache`` on :func:`get_engine`.

DuckDB with ``StaticPool`` operates on a single underlying connection, which
is both correct (no cross-process write conflicts) and efficient (no repeated
file-open cost) for an embedded file database in a single-process Streamlit app.

For the CLI (a separate process), use :func:`get_engine` directly — it keeps
its own ``@cache`` so each CLI invocation reuses the engine within that process.
"""

from __future__ import annotations

from functools import cache
from typing import override

from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel
from streamlit.connections import BaseConnection

from gptnt.common.paths import Paths

paths = Paths()


class DuckDBConnection(BaseConnection[Engine]):
    """Streamlit connection for an embedded DuckDB file database.

    Configure via ``.streamlit/secrets.toml``::

        [connections.experiments]
        db_path = "/absolute/path/to/experiments.duckdb"

    Or pass ``db_path`` inline (useful for dev/testing)::

        conn = st.connection("experiments", type=DuckDBConnection, db_path="...")
    """

    @property
    def engine(self) -> Engine:
        """The underlying SQLAlchemy Engine."""
        return self._instance

    @property
    def session(self) -> Session:
        """Return a new SQLAlchemy Session."""
        return Session(self._instance)

    def create_schema(self) -> None:
        """Create all SQLModel-registered tables.

        Safe to call repeatedly.
        """
        from gptnt.app.experiment_loader.scanner import ScannedExperiment  # noqa: PLC0415, F401

        SQLModel.metadata.create_all(self._instance)

    @override
    def _connect(self, **kwargs: object) -> Engine:
        db_path = kwargs.get("db_path") or self._secrets.get("db_path")
        if not db_path:
            db_path = str(paths.experiments_db)
        return create_engine(f"duckdb:///{db_path}", poolclass=StaticPool)


@cache
def get_engine(db_path: str) -> Engine:
    """Return a cached SQLAlchemy engine for CLI / non-Streamlit use."""
    return create_engine(f"duckdb:///{db_path}", poolclass=StaticPool)
