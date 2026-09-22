"""Beyond the Crowd Score — Streamlit app (entry point and page router)."""

from pathlib import Path

import streamlit as st

from src.app_data import display_name, list_users
from src.app_ui import inject_css

LOGO = Path(__file__).parent / "assets" / "logo.png"

st.set_page_config(page_title="Beyond the Crowd Score", page_icon=str(LOGO), layout="wide")
st.logo(str(LOGO), size="large")
inject_css()

users = list_users()
if not users:
    st.error("No processed data found. Run notebooks 01–05 on a Letterboxd export first — "
             "they write the app's files to data/processed/<username>/.")
    st.stop()

if len(users) > 1:
    st.selectbox("Whose films?", users, format_func=display_name, key="user")
else:
    st.session_state["user"] = users[0]

pages = [
    st.Page("app_pages/0_intro.py",             title="Intro", default=True),
    st.Page("app_pages/1_beyond_the_crowd.py",  title="Beyond the crowd"),
    st.Page("app_pages/2_watchlist.py",         title="Watchlist"),
    st.Page("app_pages/3_coming_soon.py",       title="Coming soon"),
]

st.navigation(pages, position="top").run()

st.markdown(
    "<p style='color:var(--muted); font-size:0.8rem; margin-top:3rem; padding-top:1rem; "
    "border-top:1px solid var(--slate)'>Built from a Letterboxd export. Film data and posters from TMDB. "
    "This product uses the TMDB API but is not endorsed or certified by TMDB.</p>",
    unsafe_allow_html=True,
)