import streamlit as st

from config import settings

st.set_page_config(
    page_title="DragonLens - Brand Visibility Tracker",
    page_icon="🐉",
    layout="wide",
)

public_pages = ["Demo Overview", "View Results", "Run Inspector", "Runs History"]
local_pages = [
    "Setup & Start",
    "View Results",
    "Run Inspector",
    "Runs History",
    "Feedback",
    "API Keys",
]
pages = public_pages if settings.is_public_demo else local_pages

page = st.sidebar.radio("Navigate", pages)

if settings.is_public_demo:
    st.sidebar.caption("Public demo mode")

if page == "Demo Overview":
    from ui.pages import demo
    demo.show()
elif page == "Setup & Start":
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
