"""Shared look and formatting for the Streamlit app.

Every rating shown in the app goes through these helpers, so units are never dropped:
predictions as half-stars (3.5 ★), crowd as 6.1 / 10, gaps as +0.8 ★.
"""

import numpy as np
import pandas as pd
import streamlit as st

POSTER_BASE = "https://image.tmdb.org/t/p/w342"

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Hanken+Grotesk:wght@400;500;600;700;800&display=swap');

:root {
    --orange:  #ff8000;
    --green:   #00e054;
    --blue:    #40bcf4;
    --dark:    #15181d;
    --surface: #2c3440;
    --slate:   #445466;
    --muted:   #98aabb;
    --white:   #ffffff;
}

html, body, .stApp, .stApp p, .stApp li, .stApp label, .stApp button, .stApp input {
    font-family: 'Hanken Grotesk', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}

.stApp h1, .stApp h2, .stApp h3 {
    font-family: 'Hanken Grotesk', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    font-weight: 700;
    letter-spacing: -0.02em;
}

.block-container, [data-testid="stMainBlockContainer"] {
    padding-top: 2.5rem;
    padding-bottom: 2rem;
    max-width: 1400px;
}

.stApp hr {
    border-color: var(--slate);
}

/* Lead paragraph under a page title */
.lead {
    font-size: 1.3rem;
    line-height: 1.5;
    color: var(--muted);
    max-width: 60rem;
    margin-bottom: 1.5rem;
}

.lead b {
    color: var(--white);
    font-weight: 600;
}

/* Poster cards: the whole card is one invisible button */
[class*="st-key-card_"] {
    position: relative;
    margin-bottom: 1.75rem;
}

[class*="st-key-card_"] img {
    border-radius: 6px;
    transition: transform 0.2s ease, box-shadow 0.2s ease;
}

[class*="st-key-card_"]:hover img {
    transform: translateY(-4px);
    box-shadow: 0 10px 24px rgba(0, 0, 0, 0.5), 0 0 0 2px var(--orange);
}

[class*="st-key-open_"] {
    position: absolute;
    inset: 0;
    z-index: 2;
}

[class*="st-key-open_"] [data-testid="stButton"],
[class*="st-key-open_"] button {
    width: 100%;
    height: 100%;
}

[class*="st-key-open_"] button {
    opacity: 0;
    cursor: pointer;
}

.card-title {
    font-weight: 600;
    font-size: 1.05rem;
    line-height: 1.25;
    margin-top: 0.4rem;
}

.card-meta {
    color: var(--muted);
    font-size: 1rem;
    line-height: 1.45;
    margin-top: 0.15rem;
}

/* Model ladder (inside the film dialog) */
.ladder-top {
    display: flex;
    align-items: center;
    gap: 1.25rem;
    margin-bottom: 0.75rem;
}

.ladder-poster {
    width: 84px;
    flex: none;
    border-radius: 6px;
}

.ladder-head {
    color: var(--muted);
    font-size: 1.05rem;
    line-height: 1.6;
}

.ladder-head b {
    color: var(--white);
}

.rung {
    display: grid;
    grid-template-columns: 17rem 1fr 6.5rem;
    align-items: center;
    gap: 1rem;
    padding: 0.4rem 0;
    border-bottom: 1px solid var(--slate);
}

.rung.new {
    animation: rung-in 0.45s ease both;
}

.rung.pending {
    opacity: 0.35;
}

.rung-label {
    font-weight: 600;
}

.rung-sub {
    color: var(--muted);
    font-size: 0.82rem;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.track {
    position: relative;
    height: 28px;
}

.track::before {
    content: "";
    position: absolute;
    left: 0;
    right: 0;
    top: 50%;
    height: 2px;
    background: var(--slate);
}

.actual {
    position: absolute;
    top: 0;
    bottom: 0;
    width: 2px;
    background: var(--green);
}

.move {
    position: absolute;
    top: 50%;
    height: 2px;
    background: var(--orange);
    opacity: 0.6;
    transform: translateY(-50%);
}

.marker {
    position: absolute;
    top: 50%;
    width: 14px;
    height: 14px;
    border-radius: 50%;
    background: var(--orange);
    transform: translate(-50%, -50%);
    z-index: 2;
}

.marker.prev {
    width: 9px;
    height: 9px;
    background: var(--muted);
    opacity: 0.7;
    z-index: 1;
}

.rung-value {
    text-align: right;
    font-weight: 700;
    font-size: 1.2rem;
}

.rung-value small {
    display: block;
    color: var(--muted);
    font-weight: 400;
    font-size: 0.8rem;
}

.rung.scale {
    border-bottom: none;
}

.track-scale {
    position: relative;
    height: 1.2rem;
}

.track-scale span {
    position: absolute;
    transform: translateX(-50%);
    color: var(--muted);
    font-size: 0.8rem;
}

.ladder-summary {
    font-size: 1.1rem;
    margin-top: 0.75rem;
    animation: rung-in 0.45s ease both;
}

.ladder-summary b {
    color: var(--white);
}

.ladder-note {
    color: var(--muted);
    font-size: 0.78rem;
    margin: 0.5rem 0 0.75rem;
    line-height: 1.45;
}

@keyframes rung-in {
    from { opacity: 0; transform: translateY(6px); }
    to   { opacity: 1; transform: none; }
}

/* Poster card figures: labels on one grid row, values on the next, so the values
   line up even when one label wraps onto two lines */
.card-stats {
    display: grid;
    column-gap: 1.25rem;
    row-gap: 0.1rem;
    justify-content: start;
    align-items: end;
    margin-top: 0.35rem;
}

.card-stats .label {
    color: var(--muted);
    font-size: 0.75rem;
    line-height: 1.25;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}

.card-stats .value {
    font-weight: 700;
    font-size: 1.15rem;
    color: var(--white);
}

/* Intro page */
.hero-kicker {
    color: var(--orange);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: 0.85rem;
    font-weight: 700;
    margin-top: 1rem;
}

.hero-title {
    font-size: clamp(3rem, 6vw, 5rem);
    font-weight: 800;
    line-height: 0.95;
    letter-spacing: -0.035em;
    margin: 0.5rem 0 1.25rem;
    color: var(--white);
}

.stats {
    display: flex;
    flex-wrap: wrap;
    gap: 3rem;
    padding: 1.5rem 0;
    margin: 1rem 0 2.5rem;
    border-top: 1px solid var(--slate);
    border-bottom: 1px solid var(--slate);
}

.stat-value {
    display: block;
    font-size: 2.6rem;
    font-weight: 800;
    letter-spacing: -0.02em;
    line-height: 1.1;
}

.stat-label {
    display: block;
    color: var(--muted);
    font-size: 0.95rem;
    max-width: 15rem;
}

.layers {
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: 1rem;
    margin: 1rem 0 1.75rem;
}

.layer {
    background: var(--surface);
    border-radius: 10px;
    border-top: 4px solid var(--slate);
    padding: 1.1rem 1.1rem 1.25rem;
}

.layer-num {
    color: var(--muted);
    font-size: 0.8rem;
    font-weight: 700;
    letter-spacing: 0.08em;
}

.layer-label {
    font-size: 1.2rem;
    font-weight: 700;
    margin: 0.2rem 0;
}

.layer-sub {
    color: var(--muted);
    font-size: 0.9rem;
    margin-bottom: 0.7rem;
}

.layer p {
    font-size: 0.95rem;
    line-height: 1.5;
    margin: 0;
}

.rule {
    border-left: 3px solid var(--green);
    padding: 0.4rem 0 0.4rem 1rem;
    margin-bottom: 1.5rem;
    color: var(--muted);
    max-width: 60rem;
    line-height: 1.5;
}

.rule b {
    color: var(--white);
}
"""


def inject_css():
    st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)


# ---------- Formatting: every number carries its unit ----------

def half_star(x):
    """Round to the nearest half-star, halves always rounding up (4.25 -> 4.5)."""
    return np.floor(x * 2 + 0.5) / 2


def stars(x):
    """Prediction or rating for display: '3.5 ★' (non-breaking space keeps the star with its number)."""
    return "—" if pd.isna(x) else f"{half_star(x):.1f}\u00a0★"


def stars_exact(x):
    """Unrounded prediction, shown small beside the half-star: '3.74 ★'."""
    return "—" if pd.isna(x) else f"{x:.2f}\u00a0★"


def crowd(x):
    """TMDB crowd score: '6.1 / 10'."""
    return "—" if pd.isna(x) else f"{x:.1f}\u00a0/\u00a010"


def gap(x):
    """Signed difference in stars, with a true minus sign: '+0.8 ★', '−0.3 ★'."""
    return "—" if pd.isna(x) else f"{x:+.1f}\u00a0★".replace("-", "−")


def poster_url(path):
    """Full TMDB poster URL, or None when the film has no poster."""
    return None if pd.isna(path) or not path else POSTER_BASE + path


# ---------- Poster cards ----------

def card_stats(pairs):
    """Small uppercase labels above large values: [('Predicted', '4.5 ★'), ('Crowd', '7.6 / 10')]."""
    labels = "".join(f"<span class='label'>{label}</span>" for label, _ in pairs)
    values = "".join(f"<span class='value'>{value}</span>" for _, value in pairs)
    return (f"<div class='card-stats' style='grid-template-columns:repeat({len(pairs)}, auto)'>"
            f"{labels}{values}</div>")


def poster_card(film, key, caption_html, on_open, id_col="film_key"):
    """Poster with a caption beneath, in a keyed container; CSS stretches the button over all of it."""
    with st.container(key=key):
        url = poster_url(film.poster_path)
        if url:
            st.image(url, width="stretch")
        else:
            st.markdown("<div style='aspect-ratio:2/3; background:var(--surface); "
                        "border-radius:6px'></div>", unsafe_allow_html=True)
        st.markdown(caption_html, unsafe_allow_html=True)
        st.button(film.film_title, key=f"open_{key}", on_click=on_open, args=(getattr(film, id_col),))


def poster_grid(films, key_prefix, caption, on_open, id_col="film_key", per_row=6):
    """Rows of poster cards; `caption(film)` returns each card's HTML, `on_open(id)` runs on click."""
    for start in range(0, len(films), per_row):
        cols = st.columns(per_row)
        for i, (col, film) in enumerate(zip(cols, films.iloc[start:start + per_row].itertuples())):
            with col:
                poster_card(film, f"card_{key_prefix}_{start + i}", caption(film), on_open, id_col)
