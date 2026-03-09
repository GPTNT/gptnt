import st_tailwind as tw
import streamlit as st

from gptnt.app.dialogue_viewer_page import render_dialogue_viewer
from gptnt.app.field_extractor_page import extractor_page

_ = tw.initialize_tailwind()
st.set_page_config(page_title="KTANE Viewer", layout="wide")


pages = st.navigation(
    [
        st.Page(render_dialogue_viewer, title="Dialogue Viewer", icon=":material/forum:"),
        st.Page(extractor_page, title="Field Extractor", icon=":material/feature_search:"),
    ],
    position="sidebar",
)


pages.run()
