import streamlit as st

from config import settings
from ui.navigation import local_pages, public_pages

st.set_page_config(
    page_title="DragonLens - Brand Visibility Tracker",
    page_icon="🐉",
    layout="wide",
)

page = st.sidebar.radio(
    "Navigate",
    public_pages() if settings.is_public_demo else local_pages(),
)

if settings.is_public_demo:
    st.sidebar.caption("Public demo mode")

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
