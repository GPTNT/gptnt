import st_tailwind as tw
import streamlit as st

from gptnt.app.dialogue_viewer_page import dialogue_viewer_page
from gptnt.app.loader_page import loader_page

_ = tw.initialize_tailwind()
st.set_page_config(page_title="KTANE Viewer", layout="wide")


dialogue_viewer_page = st.Page(
    dialogue_viewer_page, title="Dialogue Viewer", icon=":material/chat:"
)
pages = st.navigation(
    [
        st.Page(loader_page, title="Experiment Loader", icon=":material/feature_search:"),
        dialogue_viewer_page,
    ],
    position="top",
)


pages.run()
