import streamlit as st

st.set_page_config(
    page_title="DragonLens - Brand Visibility Tracker",
    page_icon="🐉",
    layout="wide",
)

page = st.sidebar.radio(
    "Navigate",
    ["Dashboard", "New Run", "Run History", "Settings"],
)

if page == "Dashboard":
    from ui.views import dashboard
    dashboard.show()
elif page == "New Run":
    from ui.views import setup
    setup.show()
elif page == "Run History":
    from ui.views import run_history
    run_history.show()
elif page == "Settings":
    from ui.views import settings
    settings.show()
