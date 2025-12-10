import streamlit as st

st.set_page_config(
    page_title="DragonLens - Brand Visibility Tracker",
    page_icon="🐉",
    layout="wide",
)

page = st.sidebar.radio(
    "Navigate",
    ["Setup & Start", "View Results", "Runs History"],
)

if page == "Setup & Start":
    from src.ui.pages import setup
    setup.show()
elif page == "View Results":
    from src.ui.pages import results
    results.show()
elif page == "Runs History":
    from src.ui.pages import history
    history.show()
