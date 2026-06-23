from __future__ import annotations

import time
from typing import TYPE_CHECKING

import pandas as pd
import streamlit as st
from code_editor import code_editor

from gptnt.app.app_state import QueryRecord, SqlViewerState, get_state
from gptnt.app.components.pagination import get_pagination_state, render_pagination_controls
from gptnt.app.components.schema_browser import render_schema_browser

if TYPE_CHECKING:
    from gptnt.experiments.db.connection import DuckDBConnection

_SQL_PAGE_SESSION_KEY = "sql_results_page"
_ALLOWED_PREFIXES = ("SELECT", "SHOW", "DESCRIBE")


def _rename_duplicate_cols(df: pd.DataFrame) -> None:
    """Rename duplicate column names in-place by appending a numeric suffix."""
    new_cols: list[str] = []
    seen: dict[str, int] = {}
    for col in df.columns:
        count = seen.get(col, 0) + 1
        seen[col] = count
        new_cols.append(col if count == 1 else f"{col}_{count}")
    df.columns = new_cols  # type: ignore[assignment]


def _coerce_arrow_incompatible_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Convert object columns that PyArrow cannot serialize (e.g. UUID) to strings."""
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].astype(str)
    return df


def _is_read_only(query: str) -> bool:
    """Return True if the query starts with an allowed read-only keyword."""
    normalised = query.strip().upper()
    return any(normalised.startswith(prefix) for prefix in _ALLOWED_PREFIXES)


def _run_query(conn: DuckDBConnection, query: str) -> tuple[pd.DataFrame, int] | None:
    """Execute a query and return (df, exec_time_ms), or None on error.

    Displays a warning and returns None if the query fails.
    """
    timer_start = time.perf_counter()
    try:
        cursor = conn.execute(query)
    except Exception as exc:  # noqa: BLE001
        _ = st.warning(str(exc), icon=":material/error:")
        return None

    col_names = [desc[0] for desc in cursor.description]
    df = pd.DataFrame(cursor.fetchall(), columns=pd.Index(col_names))

    exec_time_ms = int((time.perf_counter() - timer_start) * 1000)

    if df.columns.duplicated().any():
        _rename_duplicate_cols(df)

    return _coerce_arrow_incompatible_cols(df), exec_time_ms


def _append_to_history(
    state: SqlViewerState, query: str, exec_time_ms: int, df: pd.DataFrame
) -> None:
    """Append a query to history if it differs from the last entry."""
    history = state.query_history
    if not history or history[-1].query != query:
        history.append(
            QueryRecord(
                time=time.strftime("%X"),
                query=query,
                exec_time_ms=exec_time_ms,
                shape=(len(df), len(df.columns)),
            )
        )


def render_query_editor(current_query: str) -> str | None:
    """Render the SQL code editor and return the submitted query, or None if not submitted."""
    response = code_editor(
        current_query,
        lang="sql",
        height=[8, 20],  # pyright: ignore[reportArgumentType]
        buttons=[
            {
                "name": "Run",
                "feather": "Play",
                "primary": True,
                "hasText": True,
                "showWithIcon": True,
                "commands": ["submit"],
                "style": {"bottom": "0.5rem", "right": "0.5rem"},
                "alwaysOn": True,
            }
        ],
        response_mode="default",
        key="sql_query_editor",
    )

    if response["type"] != "submit" or not response["text"].strip():
        return None

    return response["text"].strip()


def render_metrics_strip(
    exec_time_ms: int, shape: tuple[int, int], sql_viewer: SqlViewerState
) -> None:
    """Render compact execution metrics and the page size selector in one row."""
    with st.container(horizontal=True, gap="small", vertical_alignment="center"):
        _ = st.markdown(f":small[:material/timer: {exec_time_ms} ms]", width="content")
        _ = st.markdown(f":small[:material/schedule: {time.strftime('%X')}]", width="content")
        _ = st.markdown(
            f":small[:material/grid_on: {shape[0]:,} rows · {shape[1]} cols]", width="content"
        )
        _ = st.space("stretch")

        with st.container(
            horizontal=True, gap="xsmall", vertical_alignment="center", width="content"
        ):
            _ = st.caption(":small[Rows per page]")
            page_size = st.selectbox(
                "Rows per page",
                options=[50, 100, 250],
                index=[50, 100, 250].index(sql_viewer.page_size),
                key="sql_page_size_select",
                label_visibility="collapsed",
                width=100,
                disabled=shape[0] <= 50,  # noqa: PLR2004
            )

    if page_size != sql_viewer.page_size:
        sql_viewer.page_size = page_size
        st.session_state[_SQL_PAGE_SESSION_KEY] = 0


def render_results(df: pd.DataFrame, sql_viewer: SqlViewerState) -> None:
    """Render the paginated dataframe and CSV download button."""
    pagination = get_pagination_state(
        _SQL_PAGE_SESSION_KEY, total_items=len(df), page_size=sql_viewer.page_size
    )

    _ = st.dataframe(df.iloc[pagination.start_idx : pagination.end_idx], width="stretch")

    render_pagination_controls(pagination, _SQL_PAGE_SESSION_KEY)

    _ = st.download_button(
        label=":material/download: Save to CSV",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name="query_results.csv",
        mime="text/csv",
    )


def render_history_tab(sql_viewer: SqlViewerState) -> None:
    """Render the query history tab."""
    _ = st.caption(f"Total queries: {len(sql_viewer.query_history)}")

    for record in reversed(sql_viewer.query_history):
        _ = st.divider()
        with st.container(horizontal=True, gap="small"):
            _ = st.markdown(f":small[:material/timer: {record.exec_time_ms} ms]", width="content")
            _ = st.markdown(
                f":small[:material/grid_on: {record.shape[0]:,} rows · {record.shape[1]} cols]",
                width="content",
            )
        _ = st.code(record.query, language="sql")


def render_execute_tab(conn: DuckDBConnection) -> None:
    """Render the Execute SQL tab."""
    state = get_state()

    query = render_query_editor(state.sql_viewer.current_query)
    if query is None:
        return

    state.sql_viewer.current_query = query

    if not _is_read_only(query):
        _ = st.warning(
            "Only `SELECT`, `SHOW`, and `DESCRIBE` queries are allowed.", icon=":material/block:"
        )
        return

    query_result = _run_query(conn, query)
    if query_result is None:
        return

    df, exec_time_ms = query_result
    _append_to_history(state.sql_viewer, query, exec_time_ms, df)
    render_metrics_strip(exec_time_ms, df.shape, state.sql_viewer)
    render_results(df, state.sql_viewer)


# ---------------------------------------------------------------------------
# Page entry point
# ---------------------------------------------------------------------------


def render_sql_viewer() -> None:
    """Render the SQL Explorer page."""
    state = get_state()
    conn = state.loader.connection()

    with st.sidebar:
        render_schema_browser(conn)

    tab_execute, tab_history = st.tabs(
        [":material/play_arrow: Execute SQL", ":material/history: Query History"]
    )

    with tab_execute:
        render_execute_tab(conn)

    with tab_history:
        render_history_tab(state.sql_viewer)
