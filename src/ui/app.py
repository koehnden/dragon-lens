import streamlit as st

from config import settings

st.set_page_config(
    page_title="DragonLens - Brand Visibility Tracker",
    page_icon="🐉",
    layout="wide",
)

PUBLIC_PAGES = ["Demo Overview", "Dashboard", "Run History"]
LOCAL_PAGES = ["Dashboard", "New Run", "Run History", "Settings"]

page = st.sidebar.radio(
    "Navigate",
    PUBLIC_PAGES if settings.is_public_demo else LOCAL_PAGES,
)

if settings.is_public_demo:
    st.sidebar.caption("Public demo mode")

if page == "Demo Overview":
    from ui.views import demo

    demo.show()
elif page == "Dashboard":
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
