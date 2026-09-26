import pandas as pd
import streamlit as st

from src.app_data import RUNGS, current_tables, display_name, possessive
from src.app_ui import page_title, stars

page_title()

tables  = current_tables()
summary = tables["model_summary"]
name    = display_name(st.session_state["user"])
whose   = possessive(name)

n_rated = int(summary["n_rated"])
n_test  = int(summary["n_test"])
n_watch = len(tables["watchlist"])
period  = (f"{pd.Timestamp(summary['first_watched']):%b %Y} – "
           f"{pd.Timestamp(summary['last_watched']):%b %Y}")

LAYER_DETAIL = {
    "pred_m0":     f"Predicts {stars(summary['median_rating'])}, {whose} median rating, for every film. "
                   f"The bar any real model has to clear.",
    "pred_m1":     "Uses only TMDB's average rating out of 10: what everyone else thinks. "
                   "Higher crowd score, higher prediction, in a straight line.",
    "pred_m2":     f"Adds runtime, release year, genres, original language, how many people have voted, "
                   f"popularity and whether it's part of a series. Fitted to {whose} ratings, so it learns "
                   f"their taste, not the crowd's.",
    "pred_m3":     "Adds the rating history at the moment each film was watched: the average so far for its "
                   "director, cinematographer, language, decade and genres. Only earlier films count.",
    "pred_deploy": f"Adds TMDB's plot keywords — tags like <i>coming of age</i> or <i>based on novel</i> — "
                   f"turned into a single score for how {name} tends to rate films tagged that way.",
}

LAYER_COLOUR = {        # slate: baseline · blue: the crowd · orange, green, white: the personal layers
    "pred_m0":     "var(--slate)",
    "pred_m1":     "var(--blue)",
    "pred_m2":     "var(--orange)",
    "pred_m3":     "var(--green)",
    "pred_deploy": "var(--white)",
}

st.markdown(
    f"<div class='hero-kicker'>{name} · {n_rated:,} films rated</div>"
    f"<div class='hero-title'>Beyond the<br>Crowd Score</div>"
    f"<p class='lead'>Can a model learn what one person likes, beyond what everyone else likes? "
    f"Built from {whose} Letterboxd history, every film enriched with data from TMDB.</p>",
    unsafe_allow_html=True,
)

st.markdown(
    f"<div class='stats'>"
    f"<div><span class='stat-value'>{n_rated:,}</span>"
    f"<span class='stat-label'>films rated, {period}</span></div>"
    f"<div><span class='stat-value'>{n_test}</span>"
    f"<span class='stat-label'>most recent films held back for testing, never seen in training</span></div>"
    f"<div><span class='stat-value'>{n_watch:,}</span>"
    f"<span class='stat-label'>films on the watchlist, each given a prediction</span></div>"
    f"</div>",
    unsafe_allow_html=True,
)

st.subheader("How the model learns", anchor=False)
st.markdown(
    f"<p class='lead'>The model is built up in layers. Each keeps everything before it and adds one more "
    f"kind of information, so the demo can show what each one changes. The first two are simple baselines; "
    f"the last three are Random Forests fitted to {whose} ratings.</p>",
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
    "only exists after watching it — the rating, the review — and viewing history only counts films watched "
    "before it.</div>",
    unsafe_allow_html=True,
)

st.page_link("app_pages/1_beyond_the_crowd.py", label="Start the demo →")