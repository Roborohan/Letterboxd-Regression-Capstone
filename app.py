"""Beyond the Crowd Score — Streamlit app (entry point and page router)."""

import base64
import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from src.app_data import display_name, list_users
from src.app_ui import inject_css

LOGO      = Path(__file__).parent / "assets" / "logo.png"
TMDB_LOGO = Path(__file__).parent / "assets" / "tmdb.png"
LETTERBOXD_LOGO = Path(__file__).parent / "assets" / "letterboxd.png"
QR_CODE   = Path(__file__).parent / "assets" / "qr.png"


@st.cache_data
def data_uri(path):
    """A local image as an inline data: URI — Streamlit can't serve local files inside raw HTML."""
    return "data:image/png;base64," + base64.b64encode(Path(path).read_bytes()).decode()


def setting(label, key, default, note):
    """One settings row: the switch, then its text. The text sits outside the switch's label,
    so only the switch itself toggles."""
    with st.container(horizontal=True, vertical_alignment="top", gap="medium", key=f"row_{key}"):
        st.toggle(label, value=default, key=key, label_visibility="collapsed")
        st.markdown(f"<div class='setting-label'>{label}</div>"
                    f"<div class='setting-note'>{note}</div>", unsafe_allow_html=True, width="stretch")


@st.dialog("Data sources & attribution", width="large")
def attribution():
    st.markdown(
        f"<a href='https://www.themoviedb.org/' target='_blank'>"
        f"<img src='{data_uri(str(TMDB_LOGO))}' alt='TMDB' style='height:22px'></a>"
        f"&nbsp;&nbsp;&nbsp;"
        f"<a href='https://letterboxd.com/' target='_blank'>"
        f"<img src='{data_uri(str(LETTERBOXD_LOGO))}' alt='Letterboxd' style='height:22px'></a>",
        unsafe_allow_html=True,
    )
    st.markdown(
        """
**Film data and posters** come from [TMDB](https://www.themoviedb.org/). This product uses the
TMDB API but is not endorsed or certified by TMDB. Posters remain the copyright of their
respective owners and are loaded from TMDB's image service.

**Ratings, reviews and watchlists** come from personal [Letterboxd](https://letterboxd.com/)
data exports, used with each person's permission. This app is an independent project and is
not affiliated with, endorsed by or sponsored by Letterboxd. "Letterboxd" and its logo are
trademarks of Letterboxd Limited.

**What's published:** film titles, ratings, predictions, summary figures, and short excerpts from
reviews where they help explain a prediction. Reviews are never an input to the model. Nothing
is collected from visitors to this app.

**Content:** strong language in review excerpts is always masked. Posters for films TMDB marks
as explicit are blurred by default, which can be changed in the ⚙ menu.

**Predictions** are statistical estimates from one person's history, not recommendations.

**Questions, or want your data removed?** Get in touch via
[LinkedIn](https://www.linkedin.com/in/rohan-sharma2001/).
        """
    )

st.set_page_config(page_title="Beyond the Crowd Score", page_icon=str(LOGO), layout="wide")
st.logo(str(LOGO), size="large")
inject_css()

users = list_users()
if not users:
    st.error("No processed data found. Run `python run_pipeline.py` on a Letterboxd export "
             "(or notebooks 01–05) first — they write the app's files to "
             "data/processed/<username>/.")
    st.stop()

# DEFAULT_USER (.env locally, Secrets when deployed) picks who the app opens on;
# without it the users are simply alphabetical.
load_dotenv(".env")
default = os.getenv("DEFAULT_USER")
if default in users:
    users = [default] + [u for u in users if u != default]

# One row: whose films as name pills on the left, the settings menu on the right.
with st.container(key="top_bar", horizontal=True, horizontal_alignment="distribute",
                  vertical_alignment="center", gap="small", wrap=False):
    with st.container(horizontal=True, vertical_alignment="center", gap="small", width="content"):
        if len(users) > 1:
            st.markdown("<span class='viewer-label'>Viewing</span>", unsafe_allow_html=True,
                        width="content")
            shared_user = st.query_params.get("u")          # a shared link can pick the viewer
            st.segmented_control("Whose films?", users, required=True,
                                 default=shared_user if shared_user in users else users[0],
                                 format_func=display_name, key="user", label_visibility="collapsed")
        else:
            st.session_state["user"] = users[0]
    with st.popover(":material/settings:", help="Settings"):
        st.markdown("**Settings**")
        setting("Blur explicit posters", "set_blur", True,
                "Explicit films keep their prediction, just not the image.")
        setting("Show exact predictions", "set_exact", False,
                "Cards show two decimals instead of half-stars.")
        setting("Reduce motion", "set_motion", False,
                "Turns off hover effects and the ladder's animation.")

if len(users) > 1:                      # keep the address bar in step, so it can be shared as is
    st.query_params["u"] = st.session_state["user"]

if st.session_state.get("set_motion"):
    st.markdown("<style>*, *::before, *::after { animation: none !important; "
                "transition: none !important; }</style>", unsafe_allow_html=True)

pages = [
    st.Page("app_pages/0_intro.py",             title="Intro", default=True),
    st.Page("app_pages/1_beyond_the_crowd.py",  title="Beyond the crowd"),
    st.Page("app_pages/2_watchlist.py",         title="Watchlist"),
    st.Page("app_pages/3_coming_soon.py",       title="Coming soon"),
]

st.navigation(pages, position="top").run()

tmdb_logo = (f"<img src='{data_uri(str(TMDB_LOGO))}' alt='TMDB' style='height:14px'>"
             if TMDB_LOGO.exists() else "")
qr = (f"<div class='qr-desktop'><span>Open on your phone</span>"      # hidden in the phone layout
      f"<img src='{data_uri(str(QR_CODE))}' alt='QR code for this app'></div>"
      if QR_CODE.exists() else "")

st.markdown(
    "<div style='display:flex; align-items:center; gap:0.6rem; flex-wrap:wrap; "
    "color:var(--muted); font-size:0.8rem; margin-top:3rem; padding-top:1rem; "
    "border-top:1px solid var(--slate)'>"
    f"{tmdb_logo}"
    "<span>Built from Letterboxd exports. Film data and posters from TMDB. "
    "This product uses the TMDB API but is not endorsed or certified by TMDB.</span>"
    f"{qr}"
    "</div>",
    unsafe_allow_html=True,
)

if st.button("Data sources & attribution", type="tertiary", key="attribution_link"):
    attribution()