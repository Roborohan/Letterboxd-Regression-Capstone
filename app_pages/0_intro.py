import streamlit as st

from src.app_data import RUNGS, load_tables

N_RATED = 1192          # rated viewings used for modelling (03: 1,194 rated, minus 2 TV entries)

LAYER_DETAIL = {
    "pred_m0":     "Predicts 3.5★, my median rating, for every film. The bar any real model has to clear.",
    "pred_m1":     "Uses only TMDB's average rating out of 10: what everyone else thinks. "
                   "Higher crowd score, higher prediction, in a straight line.",
    "pred_m2":     "Adds runtime, release year, genres, original language, how many people have voted, "
                   "popularity and whether it's part of a series. Fitted to my ratings, so it learns "
                   "what I like, not what the crowd likes.",
    "pred_m3":     "Adds my rating history at the moment I watched each film: my average so far for its "
                   "director, cinematographer, language, decade and genres. Only earlier films count.",
    "pred_deploy": "Adds TMDB's plot keywords — tags like <i>coming of age</i> or <i>based on novel</i> — "
                   "turned into a single score for how I tend to rate films tagged that way.",
}

LAYER_COLOUR = {        # slate: baseline · blue: the crowd · orange, green, white: the personal layers
    "pred_m0":     "var(--slate)",
    "pred_m1":     "var(--blue)",
    "pred_m2":     "var(--orange)",
    "pred_m3":     "var(--green)",
    "pred_deploy": "var(--white)",
}

tables  = load_tables()
n_test  = len(tables["test"])
n_watch = len(tables["watchlist"])

st.markdown(
    f"<div class='hero-kicker'>One viewer, {N_RATED:,} films</div>"
    "<div class='hero-title'>Beyond the<br>Crowd Score</div>"
    "<p class='lead'>Can a model learn what one person likes — beyond what everyone else likes? "
    "Built from my Letterboxd history, every film enriched with data from TMDB.</p>",
    unsafe_allow_html=True,
)

st.markdown(
    f"<div class='stats'>"
    f"<div><span class='stat-value'>{N_RATED:,}</span>"
    f"<span class='stat-label'>films I've rated and reviewed, Dec 2021 – Aug 2026</span></div>"
    f"<div><span class='stat-value'>{n_test}</span>"
    f"<span class='stat-label'>most recent films held back for testing, never seen in training</span></div>"
    f"<div><span class='stat-value'>{n_watch:,}</span>"
    f"<span class='stat-label'>films on my watchlist, each given a prediction</span></div>"
    f"</div>",
    unsafe_allow_html=True,
)

st.subheader("How the model learns", anchor=False)
st.markdown(
    "<p class='lead'>The model is built up in layers. Each keeps everything before it and adds one more "
    "kind of information, so the demo can show what each one changes. The first two are simple baselines; "
    "the last three are Random Forests fitted to my ratings.</p>",
    unsafe_allow_html=True,
)

cards = "".join(
    f"<div class='layer' style='border-top-color:{LAYER_COLOUR[col]}'>"
    f"<div class='layer-num'>LAYER {i}</div>"
    f"<div class='layer-label'>{label}</div>"
    f"<div class='layer-sub'>{sub}</div>"
    f"<p>{LAYER_DETAIL[col]}</p></div>"
    for i, (col, label, sub, _) in enumerate(RUNGS)
)
st.markdown(f"<div class='layers'>{cards}</div>", unsafe_allow_html=True)

st.markdown(
    "<div class='rule'><b>One rule throughout:</b> the final model never sees anything about a film that "
    "only exists after watching it — my rating, my review — and my history only counts films I'd watched "
    "before it.</div>",
    unsafe_allow_html=True,
)

st.page_link("app_pages/1_beyond_the_crowd.py", label="Start the demo →")