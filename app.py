"""Beyond the Crowd Score — Streamlit app (entry point and page router)."""

import streamlit as st

from src.app_ui import inject_css

st.set_page_config(page_title="Beyond the Crowd Score", page_icon="🎬", layout="wide")
inject_css()

pages = [
    st.Page("app_pages/0_intro.py",             title="Intro", default=True),
    st.Page("app_pages/1_beyond_the_crowd.py",  title="Beyond the crowd"),
    st.Page("app_pages/2_watchlist.py",         title="Your watchlist"),
    st.Page("app_pages/3_coming_soon.py",       title="Coming soon"),
]

st.navigation(pages, position="top").run()