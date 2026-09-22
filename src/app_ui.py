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
.ladder-head {
    color: var(--muted);
    font-size: 1rem;
    line-height: 1.7;
}

.ladder-head b {
    color: var(--white);
}

.rung {
    display: grid;
    grid-template-columns: 12rem 1fr 5rem;
    align-items: center;
    gap: 1rem;
    padding: 0.55rem 0;
    border-bottom: 1px solid var(--slate);
    opacity: 0;
    animation: rung-in 0.45s ease forwards;
}

.rung-label {
    font-weight: 600;
}

.rung-sub {
    color: var(--muted);
    font-size: 0.85rem;
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

.marker {
    position: absolute;
    top: 50%;
    width: 14px;
    height: 14px;
    border-radius: 50%;
    background: var(--orange);
    transform: translate(-50%, -50%);
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

.ladder-note {
    color: var(--muted);
    font-size: 0.85rem;
    margin-top: 0.8rem;
    line-height: 1.5;
}

@keyframes rung-in {
    from { opacity: 0; transform: translateY(6px); }
    to   { opacity: 1; transform: none; }
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