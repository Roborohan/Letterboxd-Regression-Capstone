import html
import math

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from src.app_data import current_tables, display_name, load_reviews, possessive
from src.app_ui import (blur_on, card_stats, censor_review, crowd, dialog_slot, excerpt, film_links,
                        flag_html, fold, gap, new_dialog, page_title, poster_grid, poster_url, pred_text, runtime_text,
                        stars, stars_exact, take_shared_film, thumb_html)

page_title("Watchlist")

PAGE_SIZE = 18
MIN_GAP   = 0.25        # a quarter-star: half the half-star step predictions are displayed in
FAVOURITES, MISSES = "Likely favourites", "Likely misses"
ABOVE, BELOW       = "Above the crowd", "Below the crowd"
MODES              = [FAVOURITES, MISSES, ABOVE, BELOW]

ALL, KNOWN, VERY = "All films", "Well known", "Very well known"
LEVELS           = [ALL, KNOWN, VERY]

# Length, in 15-minute steps; the two ends mean "no limit" (the watchlist has no films under 45m)
LENGTH_STEPS = [45] + list(range(60, 181, 15)) + [999]


def length_label(m):
    return "45m" if m == 45 else "3h+" if m == 999 else f"{m // 60}h" + (f" {m % 60}m" if m % 60 else "")

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

GENRES  = sorted({g for gs in wl["genres"].dropna() for g in gs.split("|") if g})
DECADES = [f"{d}s" for d in range(int(wl["film_year"].min()) // 10 * 10,
                                  int(wl["film_year"].max()) // 10 * 10 + 1, 10)]
FILTER_DEFAULTS = {"known": ALL, "genres": [], "decades": (DECADES[0], DECADES[-1]),
                   "length": (LENGTH_STEPS[0], LENGTH_STEPS[-1])}

# The filter widgets are keyed by a version number: Reset (or a change of viewer, whose watchlist
# has different genres and decades) bumps it, so every filter is recreated at its default.
if st.session_state.get("wl_filters_for") != st.session_state["user"]:
    st.session_state.wl_filters_for = st.session_state["user"]
    st.session_state.wl_fv = st.session_state.get("wl_fv", 0) + 1


def fkey(name):
    return f"wl_{name}_{st.session_state.wl_fv}"


def fval(name):
    """A filter's current value, or its default before its widget has been drawn."""
    return st.session_state.get(fkey(name), FILTER_DEFAULTS[name])


def reset_paging():
    st.session_state.wl_page = 0


def reset_filters():
    st.session_state.wl_fv += 1
    reset_paging()


def active_filters():
    """Plain-English descriptions of the filters currently set, for the button count and the note."""
    out = []
    if fval("known") != ALL:
        out.append(fval("known").lower())
    if fval("genres"):
        out.append(" or ".join(fval("genres")))
    lo, hi = fval("decades")
    if (lo, hi) != FILTER_DEFAULTS["decades"]:
        out.append(lo if lo == hi else f"{lo}–{hi}")
    lo, hi = fval("length")
    if (lo, hi) != FILTER_DEFAULTS["length"]:
        if lo == LENGTH_STEPS[0]:
            out.append(f"under {length_label(hi)}")
        elif hi == LENGTH_STEPS[-1]:
            out.append(f"over {length_label(lo)}")
        else:
            out.append(f"{length_label(lo)}–{length_label(hi)}")
    return out


def go_to(page):
    st.session_state.wl_page = page
    st.session_state.wl_scroll_to_top = True


def page_typed():
    st.session_state.wl_page = st.session_state.wl_page_input - 1
    st.session_state.wl_scroll_to_top = True


def open_watchlist_film(uri):
    st.session_state.wl_open = uri
    new_dialog()


# ---------- Header and controls ----------

st.header("Watchlist", anchor=False)
st.markdown(
    f"<p class='lead'>{len(wl):,} films on {whose} watchlist, each given a predicted rating. "
    f"Predictions are compressed — between <b>{wl['pred'].min():.2f}</b> and <b>{wl['pred'].max():.2f}&nbsp;★</b> "
    f"— so read each list as likely, not as a strict ranking.</p>",
    unsafe_allow_html=True,
)

query = st.text_input("Search the watchlist", key="wl_search", placeholder="Search the watchlist",
                      icon=":material/search:", label_visibility="collapsed", on_change=reset_paging,
                      width=420).strip()

with st.container(key="wl_controls", horizontal=True, vertical_alignment="center", gap="small"):
    mode = st.segmented_control("Sort", MODES, default=FAVOURITES, key="wl_mode",
                                label_visibility="collapsed", on_change=reset_paging) or FAVOURITES
    applied = active_filters()
    with st.popover(f"Filters · {len(applied)}" if applied else "Filters", icon=":material/tune:"):
        st.select_slider(
            "How well known?", LEVELS, value=FILTER_DEFAULTS["known"], key=fkey("known"),
            on_change=reset_paging,
            help=f"Well known: at least {summary['rated_median_votes']:,.0f} TMDB votes, as well "
                 f"known as a typical film {name} has rated. Very well known: at least "
                 f"{summary['rated_votes_p75']:,.0f}, better known than three-quarters of them.",
        )
        st.multiselect("Genres", GENRES, default=[], key=fkey("genres"), on_change=reset_paging,
                       placeholder="Any genre", help="Films with any of the chosen genres.")
        st.select_slider("Decades", DECADES, value=FILTER_DEFAULTS["decades"], key=fkey("decades"),
                         on_change=reset_paging)
        st.select_slider("Length", LENGTH_STEPS, value=FILTER_DEFAULTS["length"], key=fkey("length"),
                         format_func=length_label, on_change=reset_paging)
        if applied:
            st.button("Reset filters", on_click=reset_filters, type="tertiary",
                      icon=":material/restart_alt:")
level = fval("known")

crowd_range = (f"the crowd score is between {summary['crowd_lo']:.1f} and {summary['crowd_hi']:.1f}/10, "
               f"the range where the model and the crowd can be fairly compared")
average     = f"{whose} average of {summary['rated_mean']:.2f}&nbsp;★"
explain = {
    FAVOURITES: f"Films the model expects {name} to rate at or above {average}, highest first.",
    MISSES:     f"Films the model expects {name} to rate below {average}, lowest first.",
    ABOVE:      f"Films the model expects {name} to like at least a quarter-star more than its crowd-based "
                f"estimate, and at or above {average}. Shown only where {crowd_range}.",
    BELOW:      f"Films the model expects {name} to like at least a quarter-star less than its crowd-based "
                f"estimate, and below {average}. Shown only where {crowd_range}.",
}[mode]
if query:
    explain = (f"Films on {whose} watchlist matching “{html.escape(query)}”, highest prediction first. "
               f"A search covers the whole watchlist, so the list and filter above don't apply.")
if applied and not query:
    explain += (f" <span style='color:var(--white)'>Filtered to "
                f"{html.escape(' · '.join(applied))}.</span>")
st.markdown(f"<p class='card-meta'>{explain}</p>", unsafe_allow_html=True)
st.markdown("<p class='card-meta'><span style='color:var(--orange)'>⚑</span> marks a film unlike "
            f"anything in {whose} rated history on one of the model's inputs, so its prediction is "
            "less reliable. Open a film for details.</p>", unsafe_allow_html=True)


# ---------- Filter, sort and page ----------

films = wl
mean  = summary["rated_mean"]

if query:                                   # a search covers the whole watchlist
    films = (films[films["film_title"].map(fold).str.contains(fold(query), regex=False)]
             .sort_values(["pred", "vote_count"], ascending=[False, False]))
else:
    if level != ALL:
        cut = summary["rated_median_votes"] if level == KNOWN else summary["rated_votes_p75"]
        films = films[films["vote_count"] >= cut]
    if fval("genres"):
        wanted = set(fval("genres"))
        films = films[films["genres"].fillna("").str.split("|").map(lambda gs: bool(wanted & set(gs)))]
    lo, hi = (int(d[:-1]) for d in fval("decades"))
    films = films[films["film_year"].between(lo, hi + 9)]
    lo, hi = fval("length")
    if lo > LENGTH_STEPS[0]:
        films = films[films["runtime"] >= lo]
    if hi < LENGTH_STEPS[-1]:
        films = films[films["runtime"] <= hi]

    if mode == FAVOURITES:
        films = films[films["pred"] >= mean].sort_values(["pred", "vote_count"], ascending=[False, False])
    elif mode == MISSES:
        films = films[films["pred"] < mean].sort_values(["pred", "vote_count"], ascending=[True, False])
    elif mode == ABOVE:
        films = (films[(films["gap"] >= MIN_GAP) & (films["pred"] >= mean)]
                 .sort_values(["gap", "vote_count"], ascending=[False, False]))
    else:
        films = (films[(films["gap"] <= -MIN_GAP) & (films["pred"] < mean)]
                 .sort_values(["gap", "vote_count"], ascending=[True, False]))

n_pages    = max(1, math.ceil(len(films) / PAGE_SIZE))
page       = min(st.session_state.wl_page, n_pages - 1)
start      = page * PAGE_SIZE
page_films = films.iloc[start:start + PAGE_SIZE]


# ---------- Why? ----------

def reliability_notes(film):
    """One sentence per out-of-range flag, quoting the film's value against the rated range."""
    s = summary
    flags = film["out_of_range"].split("|") if isinstance(film["out_of_range"], str) and film["out_of_range"] else []
    notes = []
    for f in flags:
        if f == "runtime":
            if pd.isna(film["runtime"]) or film["runtime"] <= 0:
                notes.append("TMDB lists no runtime for it, which the model reads as far shorter than "
                             "anything it was trained on.")
            elif film["runtime"] > s["runtime_max"]:
                notes.append(f"At {runtime_text(film['runtime'])} it's longer than any film {name} has rated "
                             f"(longest: {runtime_text(s['runtime_max'])}).")
            else:
                notes.append(f"At {runtime_text(film['runtime'])} it's shorter than any film {name} has rated "
                             f"(shortest: {runtime_text(s['runtime_min'])}).")
        elif f == "vote_average":
            side, bound = (("higher", "highest"), s["vote_average_max"]) \
                if film["vote_average"] > s["vote_average_max"] else (("lower", "lowest"), s["vote_average_min"])
            notes.append(f"Its crowd score, {crowd(film['vote_average'])}, is {side[0]} than any film {name} "
                         f"has rated ({side[1]}: {crowd(bound)}).")
        elif f == "film_year":
            older = film["film_year"] < s["film_year_min"]
            notes.append(f"Released in {film['film_year']}, it's {'older' if older else 'newer'} than any film "
                         f"{name} has rated ({'earliest' if older else 'latest'}: "
                         f"{int(s['film_year_min'] if older else s['film_year_max'])}).")
        elif f == "genre":
            genres = film["genres"].replace("|", ", ") if isinstance(film["genres"], str) and film["genres"] else "none listed"
            notes.append(f"Its genres ({genres}) are ones the model never learned — {name} rated too few "
                         f"films in them for genre to become a feature — so it predicts without genre information.")
        elif f == "popularity":
            notes.append(f"Its TMDB popularity is outside the range of every film {name} has rated.")
        else:
            notes.append(f"Its {f.replace('_', ' ')} is outside the range of {whose} rated films.")
    return notes


def neighbour_card(n):
    """A rated film as a compact row: small poster, then title, year, rating and share beside it."""
    url   = poster_url(n.neighbour_poster)
    title = html.escape(n.neighbour_title)
    if url and not (n.neighbour_sensitive and blur_on()):
        frame = f"<div class='poster-frame' style='margin:0'><img src='{url}' alt='{title}'></div>"
    elif url:
        frame = f"<div class='poster-frame poster-hidden' style='margin:0'><img src='{url}' alt=''></div>"
    else:
        frame = "<div class='poster-frame' style='margin:0'></div>"
    return (f"<div style='display:flex; gap:0.9rem; align-items:center'>"
            f"<div style='width:80px; flex:none'>{frame}</div>"
            f"<div><div class='card-title' style='margin-top:0'>{title}</div>"
            f"<div class='card-meta'>{n.neighbour_year} · rated <b style='color:var(--white)'>"
            f"{stars(n.neighbour_rating)}</b></div>"
            f"<div class='card-meta'>{n.share:.1%} of the prediction</div></div></div>")


def why_dialog(film):
    @st.dialog(film["film_title"], width="large", on_dismiss="rerun")
    def show():
        url = poster_url(film["poster_path"])
        thumb = thumb_html(url, bool(film["sensitive_poster"]))
        facts = " · ".join(str(x) for x in [film["film_year"], runtime_text(film["runtime"]), film["director"]]
                           if pd.notna(x) and x)
        genres = film["genres"].replace("|", ", ") if isinstance(film["genres"], str) else ""
        st.markdown(f"<div class='ladder-top'>{thumb}<div class='ladder-head'>{html.escape(facts)}"
                    + (f"<br>{html.escape(genres)}" if genres else "") + "</div></div>",
                    unsafe_allow_html=True)
        if isinstance(film["overview"], str) and film["overview"].strip():
            st.markdown(f"<p class='card-meta' style='max-width:55rem; margin-bottom:0.8rem'>"
                        f"{html.escape(film['overview'])}</p>", unsafe_allow_html=True)

        has_gap = pd.notna(film["gap"])
        st.markdown(
            card_stats([("Predicted", stars(film["pred"])), ("Crowd", crowd(film["vote_average"])),
                        ("Vs crowd est.", gap(film["gap"]) if has_gap else "—")])
            + f"<p class='card-meta' style='margin-top:0.6rem'>Unrounded prediction {stars_exact(film['pred'])}; "
              f"the crowd score alone would predict {stars_exact(film['crowd_pred'])}."
            + ("" if has_gap else
               f" No gap is shown: its crowd score is outside {summary['crowd_lo']:.1f}–"
               f"{summary['crowd_hi']:.1f}/10, where the two can't be fairly compared.")
            + "</p>",
            unsafe_allow_html=True,
        )

        rows = tables["neighbours"]
        rows = rows[rows["film_uri"] == film["film_uri"]].sort_values("rank")
        if not rows.empty:
            top3, top5 = rows.head(3)["share"].sum(), rows["share"].sum()
            st.subheader("Films the model drew from", anchor=False)
            st.markdown(
                "<div class='neighbours'>"
                + "".join(neighbour_card(n) for n in rows.head(3).itertuples()) + "</div>"
                + f"<p class='card-meta' style='margin-top:0.75rem'>The prediction is almost exactly a weighted "
                  f"average of {whose} ratings. These three carry the most weight — {top3:.0%} between them, "
                  f"{top5:.0%} for the top five — and the rest is spread across the other rated films.</p>",
                unsafe_allow_html=True,
            )

            reviews = load_reviews(st.session_state["user"])
            quoted = [(n, reviews.get(n.neighbour_key)) for n in rows.head(3).itertuples()]
            quoted = [(n, r) for n, r in quoted if r]
            if quoted:
                with st.expander(f"What {name} wrote about them"):
                    st.markdown(
                        "".join(f"<div style='border-left:3px solid var(--slate); padding:0.2rem 0 0.2rem 0.9rem; "
                                f"margin-bottom:0.8rem'><div class='card-title' style='margin-top:0'>"
                                f"{html.escape(n.neighbour_title)}</div><div class='card-meta'><i>“"
                                f"{html.escape(excerpt(censor_review(r)))}”</i></div></div>" for n, r in quoted)
                        + "<p class='card-meta'>Shown to explain the prediction, not part of it: review text is "
                          "never an input to the model.</p>",
                        unsafe_allow_html=True,
                    )

        notes = reliability_notes(film)
        if notes:
            st.subheader("Why this prediction is less reliable", anchor=False)
            st.markdown("".join(f"<p class='card-meta'>⚑ {n}</p>" for n in notes), unsafe_allow_html=True)

        film_links(film)

    show()


# ---------- Grid ----------

def watchlist_caption(film):
    meta = " · ".join(x for x in [str(film.film_year), runtime_text(film.runtime)] if x and x != "<NA>")
    if mode in (ABOVE, BELOW) and not query:
        second = ("Vs crowd est.", gap(film.gap))
    else:
        second = ("Crowd", crowd(film.vote_average))
    return (f"<div class='card-meta'>{meta}</div>"
            + card_stats([("Predicted", pred_text(film.pred)), second])
            + flag_html(film.out_of_range))


def pager(where):
    """First / previous / typed page number / next / last; `where` keeps widget keys distinct.

    Wrapped in a keyed container so the phone layout can hide First, Last and the labels.
    """
    last = n_pages - 1
    with st.container(key=f"pager_{where}"):
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
            st.markdown(f"<p class='card-meta' style='margin:0'>of {n_pages}</p>",
                        unsafe_allow_html=True)
        with next_col:
            st.button("Next →", key=f"next_{where}", disabled=page >= last,
                      on_click=go_to, args=(page + 1,), width="stretch")
        with last_col:
            st.button("Last ⇥", key=f"last_{where}", disabled=page >= last,
                      on_click=go_to, args=(last,), width="stretch")


if films.empty:
    if query:
        st.info(f"No watchlist films match “{query}”.")
    else:
        st.info("No films match these settings. Try widening the filters.")
        if applied:
            st.button("Reset filters", on_click=reset_filters, key="reset_empty")
else:
    st.markdown(f"<p class='card-meta'>Films {start + 1}–{start + len(page_films)} of {len(films):,}</p>",
                unsafe_allow_html=True)
    poster_grid(page_films, "watchlist", watchlist_caption, open_watchlist_film, id_col="film_uri")
    pager("bottom")

if st.session_state.pop("wl_scroll_to_top", False):
    st.session_state.wl_scroll_n = st.session_state.get("wl_scroll_n", 0) + 1
    components.html(SCROLL_TOP_JS + f"<!-- {st.session_state.wl_scroll_n} -->", height=0)

shared = take_shared_film()
if shared is not None:
    match = wl.loc[wl["tmdb_id"] == shared]
    if not match.empty:
        st.session_state.wl_open = match.iloc[0]["film_uri"]
        new_dialog()

opened = st.session_state.pop("wl_open", None)
if opened is not None:
    match = wl.loc[wl["film_uri"] == opened]
    if not match.empty:
        with dialog_slot():
            why_dialog(match.iloc[0])
