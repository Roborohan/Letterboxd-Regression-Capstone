"""Beyond the Crowd Score — Streamlit app (entry point and page router)."""

import streamlit as st

from src.app_ui import inject_css

st.set_page_config(page_title="Beyond the Crowd Score", page_icon="🎬", layout="wide")
inject_css()

pages = [
    st.Page("app_pages/1_does_it_work.py",             title="01 · Does it work?", default=True),
    st.Page("app_pages/2_what_made_the_difference.py", title="02 · What changed?"),
    st.Page("app_pages/3_is_it_useful.py",             title="03 · Your watchlist"),
    st.Page("app_pages/4_why.py",                      title="04 · Why?"),
    st.Page("app_pages/5_coming_soon.py",              title="Coming soon"),
    st.Page("app_pages/6_findings.py",                 title="Findings"),
]

st.navigation(pages, position="top").run()