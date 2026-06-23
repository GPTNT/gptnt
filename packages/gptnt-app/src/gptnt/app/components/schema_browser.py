import streamlit as st

from gptnt.experiments.db.connection import DuckDBConnection


def render_schema_browser(conn: DuckDBConnection) -> None:
    """Render a DuckDB schema browser in the sidebar."""
    _ = st.caption(":material/database: **Schema**")

    tables_result = conn.execute("SHOW TABLES")
    table_names: list[str] = [row[0] for row in tables_result.fetchall()]

    if not table_names:
        _ = st.caption(":gray[No tables found]")
        return

    parts: list[str] = [
        "<dl style='font-family:monospace; font-size:0.8rem; line-height:1.6; margin:0;'>"
    ]
    for table in sorted(table_names):
        desc = conn.execute(f"DESCRIBE {table}")
        rows = desc.fetchall()

        parts.append(f"<dt style='font-weight:bold; margin-top:0.75rem;'>* {table}:</dt>")
        for row in rows:
            col_name: str = row[0]
            col_type: str = row[1]
            parts.append(
                f"<dd style='margin:0 0 0 1rem;'>"
                f"- {col_name}&nbsp;&nbsp;"
                f"<span style='opacity:0.55;'>{col_type}</span>"
                f"</dd>"
            )

    parts.append("</dl>")
    _ = st.markdown("\n".join(parts), unsafe_allow_html=True)
