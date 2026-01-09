import streamlit as st

st.set_page_config(
    page_title="DragonLens - Brand Visibility Tracker",
    page_icon="🐉",
    layout="wide",
)

page = st.sidebar.radio(
    "Navigate",
    ["Setup & Start", "View Results", "Run Inspector", "Runs History", "Feedback", "API Keys"],
)

if page == "Setup & Start":
    from ui.pages import setup
    setup.show()
elif page == "View Results":
    from ui.pages import results
    results.show()
elif page == "Run Inspector":
    from ui.pages import run_inspector
    run_inspector.show()
elif page == "Runs History":
    from ui.pages import history
    history.show()
elif page == "Feedback":
    from ui.pages import feedback
    feedback.show()
elif page == "API Keys":
    from ui.pages import api_keys
    api_keys.show()
