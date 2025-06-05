import streamlit as st

# Import your app functions
from analyse_results import main as app1_main
from view_dialogue import main as app2_main

# Set page configuration for better performance
st.set_page_config(
    page_title="GPTNT Results Visualizer", layout="wide", initial_sidebar_state="expanded"
)

st.title("GPTNT Results Visualizer")


# Initialize session state variables for both apps
def initialize_session_state():
    # For analyse_results
    if "results_data_loaded" not in st.session_state:
        st.session_state.results_data_loaded = False
    if "df" not in st.session_state:
        st.session_state.df = None
    if "aggregate_metrics" not in st.session_state:
        st.session_state.aggregate_metrics = []

    # For view_dialogue
    if "dialogue_data_loaded" not in st.session_state:
        st.session_state.dialogue_data_loaded = False
    if "dialogue_game_id" not in st.session_state:
        st.session_state.dialogue_game_id = None
    if "dialogue_data" not in st.session_state:
        st.session_state.dialogue_data = {}


# Initialize session state before navigation
initialize_session_state()

# Wrap functions in st.Page objects with unique URL pathnames
pages = [
    st.Page(app1_main, title="Analyse Results", url_path="analyse"),
    st.Page(app2_main, title="View Dialogue", url_path="dialogue"),
]

pg = st.navigation(pages)
pg.run()
