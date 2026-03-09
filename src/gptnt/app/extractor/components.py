import streamlit as st

from gptnt.app.extractor.path_validator import validate_path


def _parse_fields(raw: str) -> list[str]:
    """Parse newline-separated field paths, stripping blanks."""
    return [line.strip() for line in raw.splitlines() if line.strip()]


def render_field_input() -> tuple[list[str], bool]:
    """Render the field path input widget with real-time per-field validation.

    Returns:
        A tuple of `(fields, all_valid)` where:
        - `fields` is the parsed list of field path strings entered by the user.
        - `all_valid` is True only when at least one field is entered and all pass
          validation. Use this to gate the Extract button.
    """
    with st.container(horizontal=True, vertical_alignment="bottom"):
        with st.container():
            fields_input = st.text_area(
                "Fields to extract (one per line)",
                placeholder="bomb_state.modules[].module_name\nerror_type[]\nstep",
                height=120,
            )
            fields = _parse_fields(fields_input)

            all_valid = True
            for field in fields:
                try:
                    validate_path(field)
                except AttributeError as err:
                    all_valid = False
                    _ = st.error(f"**{field}** — {err}", icon=":material/close:")

        extract_button = st.button("Extract", disabled=not all_valid, type="primary")

    return fields, extract_button
