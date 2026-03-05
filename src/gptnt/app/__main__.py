import st_tailwind as tw
import streamlit as st

from gptnt.app.dialogue_viewer_page import dialogue_viewer_page
from gptnt.app.field_extractor_page import extractor_page
from gptnt.app.loader_page import loader_page

_ = tw.initialize_tailwind()
st.set_page_config(page_title="KTANE Viewer", layout="wide")


pages = st.navigation(
    [
        st.Page(loader_page, title="Experiment Loader", icon=":material/feature_search:"),
        st.Page(dialogue_viewer_page, title="Dialogue Viewer", icon=":material/chat:"),
        st.Page(extractor_page, title="Field Extractor", icon=":material/dentistry:"),
    ],
    position="top",
)


pages.run()
