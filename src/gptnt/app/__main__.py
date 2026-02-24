import st_tailwind as tw
import streamlit as st

from gptnt.app.dialogue_viewer_page import dialogue_viewer_page
from gptnt.app.results_page import results_page

_ = tw.initialize_tailwind()
st.set_page_config(page_title="KTANE Viewer", layout="wide")


pages = st.navigation(
    [
        st.Page(dialogue_viewer_page, title="Dialogue Viewer", icon=":material/chat:"),
        st.Page(results_page, title="Experiment Results", icon=":material/query_stats:"),
    ],
    position="top",
)

pages.run()
