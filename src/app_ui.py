"""Shared look and formatting for the Streamlit app.

Every rating shown in the app goes through these helpers, so units are never dropped:
predictions as half-stars (3.5 ★), crowd as 6.1 / 10, gaps as +0.8 ★.
"""

import numpy as np
import pandas as pd
import streamlit as st

POSTER_BASE = "https://image.tmdb.org/t/p/w342"

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

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
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}

.stApp h1, .stApp h2, .stApp h3 {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    font-weight: 700;
    letter-spacing: -0.02em;
}

.block-container, [data-testid="stMainBlockContainer"] {
    padding-top: 2.5rem;
    max-width: 1400px;
}

.stApp hr {
    border-color: var(--slate);
}
"""


def inject_css():
    st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)


# ---------- Formatting: every number carries its unit ----------

def half_star(x):
    """Round to the nearest half-star, halves always rounding up (4.25 -> 4.5)."""
    return np.floor(x * 2 + 0.5) / 2


def stars(x):
    """Prediction or rating for display: '3.5 ★'."""
    return "—" if pd.isna(x) else f"{half_star(x):.1f} ★"


def stars_exact(x):
    """Unrounded prediction, shown small beside the half-star: '3.74 ★'."""
    return "—" if pd.isna(x) else f"{x:.2f} ★"


def crowd(x):
    """TMDB crowd score: '6.1 / 10'."""
    return "—" if pd.isna(x) else f"{x:.1f} / 10"


def gap(x):
    """Signed difference in stars, with a true minus sign: '+0.8 ★', '−0.3 ★'."""
    return "—" if pd.isna(x) else f"{x:+.1f} ★".replace("-", "−")


def poster_url(path):
    """Full TMDB poster URL, or None when the film has no poster."""
    return None if pd.isna(path) or not path else POSTER_BASE + path