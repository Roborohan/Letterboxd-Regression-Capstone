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