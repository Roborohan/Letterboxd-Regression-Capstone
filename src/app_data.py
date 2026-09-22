"""App data loading — moved from app.py.

Reads only data/processed/, the committed app tables.
"""

from pathlib import Path

import pandas as pd
import streamlit as st

DATA = Path(__file__).resolve().parent.parent / "data" / "processed"

TABLES = {
    "test":       "test_predictions.csv",
    "watchlist":  "watchlist_predictions.csv",
    "neighbours": "neighbours.csv",
    "coming":     "coming_soon.csv",
}

EXPECTED_ROWS = {"test": 239, "watchlist": 3924, "neighbours": 19620, "coming": 29}

ID_COLS = ["tmdb_id", "film_year", "neighbour_tmdb_id", "neighbour_year"]


@st.cache_data
def load_tables():
    tables = {}
    for name, filename in TABLES.items():
        df = pd.read_csv(DATA / filename)
        for col in ID_COLS:
            if col in df.columns:
                df[col] = df[col].astype("Int64")
        tables[name] = df
    return tables

# The model ladder: (prediction column, label, what the model knows, button text to add this layer).
# Shared by the intro page and the Beyond the crowd modal so the labels can't drift apart.
RUNGS = [
    ("pred_m0",     "Knows nothing",  "My typical rating, same for every film",        None),
    ("pred_m1",     "+ Crowd score",  "TMDB's average rating",                         "Add the crowd score"),
    ("pred_m2",     "+ Film details", "Genre, runtime, era, language",                 "Add film details"),
    ("pred_m3",     "+ My history",   "My past ratings of its director, genres, era",  "Add my history"),
    ("pred_deploy", "+ Keywords",     "TMDB plot keywords — the final model",          "Add keywords"),
]