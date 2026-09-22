import math

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from src.app_data import current_tables, display_name, possessive
from src.app_ui import card_stats, crowd, gap, poster_grid, stars

PAGE_SIZE = 18
MIN_GAP   = 0.25        # a quarter-star: half the half-star step predictions are displayed in
FAVOURITES, ABOVE = "Likely favourites", "Above the crowd"

SCROLL_TOP_JS = """
<script>
const doc = window.parent.document;
[doc.querySelector('[data-testid="stMain"]'),
 doc.querySelector('[data-testid="stAppViewContainer"]'),
 doc.querySelector('section.main'),
 doc.scrollingElement].forEach(el => { if (el) el.scrollTo({top: 0, behavior: "smooth"}); });
window.parent.scrollTo({top: 0, behavior: "smooth"});
</script>
"""

tables  = current_tables()
wl      = tables["watchlist"]
summary = tables["watchlist_summary"]
name    = display_name(st.session_state["user"])
whose   = possessive(name)

if "wl_page" not in st.session_state:
    st.session_state.wl_page = 0


def reset_paging():
    st.session_state.wl_page = 0


def go_to(page):
    st.session_state.wl_page = page
    st.session_state.wl_scroll_to_top = True


def page_typed():
    st.session_state.wl_page = st.session_state.wl_page_input - 1
    st.session_state.wl_scroll_to_top = True


def open_watchlist_film(uri):
    st.session_state.wl_open = uri


def runtime_text(minutes):
    if pd.isna(minutes) or minutes <= 0:
        return None
    h, m = divmod(int(minutes), 60)
    return f"{h}h {m}m" if h else f"{m}m"


# ---------- Header and controls ----------

st.header("Watchlist", anchor=False)
st.markdown(
    f"<p class='lead'>{len(wl):,} films on {whose} watchlist, each given a predicted rating. "
    f"Predictions are compressed — none above <b>{wl['pred'].max():.2f}&nbsp;★</b> — so read the top "
    f"as likely favourites, not a strict ranking.</p>",
    unsafe_allow_html=True,
)

left, right = st.columns([3, 2])
with left:
    mode = st.segmented_control("Sort", [FAVOURITES, ABOVE], default=FAVOURITES, key="wl_mode",
                                label_visibility="collapsed", on_change=reset_paging) or FAVOURITES
with right:
    well_known = st.toggle(
        "Well-known films only", key="wl_known", on_change=reset_paging,
        help=f"At least {summary['rated_median_votes']:,.0f} TMDB votes — as well known as a typical "
             f"film {name} has rated.",
    )

if mode == ABOVE:
    explain = (f"Films the model expects {name} to like at least a quarter-star more than its "
               f"crowd-based estimate. Shown only where the crowd score is between "
               f"{summary['crowd_lo']:.1f} and {summary['crowd_hi']:.1f}/10, the range where the two can "
               f"be fairly compared, and the prediction is at least {whose} average of "
               f"{summary['rated_mean']:.2f}&nbsp;★.")
else:
    explain = f"Films the model expects {name} to rate highly."
st.markdown(f"<p class='card-meta'>{explain}</p>", unsafe_allow_html=True)


# ---------- Filter, sort and page ----------

films = wl
if well_known:
    films = films[films["vote_count"] >= summary["rated_median_votes"]]

if mode == ABOVE:
    films = (films[(films["gap"] >= MIN_GAP) & (films["pred"] >= summary["rated_mean"])]
             .sort_values(["gap", "vote_count"], ascending=False))
else:
    films = films.sort_values(["pred", "vote_count"], ascending=False)

n_pages    = max(1, math.ceil(len(films) / PAGE_SIZE))
page       = min(st.session_state.wl_page, n_pages - 1)
start      = page * PAGE_SIZE
page_films = films.iloc[start:start + PAGE_SIZE]


# ---------- Grid ----------

def watchlist_caption(film):
    meta = " · ".join(x for x in [str(film.film_year), runtime_text(film.runtime)] if x and x != "<NA>")
    if mode == ABOVE:
        second = ("Vs crowd est.", gap(film.gap))
    else:
        second = ("Crowd", crowd(film.vote_average))
    flag = ("<div style='color:var(--orange); font-size:0.8rem; margin-top:0.2rem'>⚑ unusual data</div>"
            if isinstance(film.out_of_range, str) and film.out_of_range else "")
    return (f"<div class='card-meta'>{meta}</div>"
            + card_stats([("Predicted", stars(film.pred)), second])
            + flag)


def pager(where):
    """First / previous / typed page number / next / last; `where` keeps widget keys distinct."""
    last = n_pages - 1
    first_col, prev_col, label_col, input_col, of_col, next_col, last_col, _ = st.columns(
        [1.1, 1.3, 0.5, 0.9, 0.8, 1.3, 1.1, 3], vertical_alignment="center")

    with first_col:
        st.button("⇤ First", key=f"first_{where}", disabled=page == 0,
                  on_click=go_to, args=(0,), width="stretch")
    with prev_col:
        st.button("← Previous", key=f"prev_{where}", disabled=page == 0,
                  on_click=go_to, args=(page - 1,), width="stretch")
    with label_col:
        st.markdown("<p class='card-meta' style='text-align:right; margin:0'>Page</p>",
                    unsafe_allow_html=True)
    with input_col:
        st.session_state.wl_page_input = page + 1          # always shows the current page
        st.number_input("Page", min_value=1, max_value=n_pages, step=1, key="wl_page_input",
                        label_visibility="collapsed", on_change=page_typed)
    with of_col:
        st.markdown(f"<p class='card-meta' style='margin:0'>of {n_pages}</p>", unsafe_allow_html=True)
    with next_col:
        st.button("Next →", key=f"next_{where}", disabled=page >= last,
                  on_click=go_to, args=(page + 1,), width="stretch")
    with last_col:
        st.button("Last ⇥", key=f"last_{where}", disabled=page >= last,
                  on_click=go_to, args=(last,), width="stretch")

if films.empty:
    st.info("No films match these settings.")
else:
    st.markdown(f"<p class='card-meta'>Films {start + 1}–{start + len(page_films)} of {len(films):,}</p>",
                unsafe_allow_html=True)
    poster_grid(page_films, "watchlist", watchlist_caption, open_watchlist_film, id_col="film_uri")
    pager("bottom")


if st.session_state.pop("wl_scroll_to_top", False):
    st.session_state.wl_scroll_n = st.session_state.get("wl_scroll_n", 0) + 1
    components.html(SCROLL_TOP_JS + f"<!-- {st.session_state.wl_scroll_n} -->", height=0)

# ---------- Why? (next piece) ----------

opened = st.session_state.pop("wl_open", None)
if opened is not None:
    film = wl.loc[wl["film_uri"] == opened].iloc[0]

    @st.dialog(film["film_title"], width="large")
    def why():
        st.write("The Why? view goes here.")

    why()