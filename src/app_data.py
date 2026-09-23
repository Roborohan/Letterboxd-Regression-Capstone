"""App data loading.

Each Letterboxd export gets its own folder, data/processed/<username>/, written by
notebooks 01, 04 and 05. The app lists the folders that are complete and loads one.
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

SUMMARIES = {                     # one-row files, loaded as dictionaries
    "profile":           "profile.csv",
    "model_summary":     "model_summary.csv",
    "watchlist_summary": "watchlist_summary.csv",
}

ID_COLS = ["tmdb_id", "film_year", "neighbour_tmdb_id", "neighbour_year"]

# The model ladder: (prediction column, label, what the model knows, button text to add this layer).
# Shared by the intro page and the Beyond the crowd modal so the labels can't drift apart.
RUNGS = [
    ("pred_m0",     "Knows nothing",      "Typical rating, same for every film",        None),
    ("pred_m1",     "+ Crowd score",      "TMDB's average rating",                      "Add the crowd score"),
    ("pred_m2",     "+ Film details",     "Genre, runtime, era, language",              "Add film details"),
    ("pred_m3",     "+ Viewing history",  "Past ratings of its director, genres, era",  "Add viewing history"),
    ("pred_deploy", "+ Keywords",         "TMDB plot keywords — the final model",       "Add keywords"),
]

def list_users():
    """Usernames whose folder holds every file the app needs, sorted."""
    needed = list(TABLES.values()) + list(SUMMARIES.values())
    if not DATA.is_dir():
        return []
    return sorted(p.name for p in DATA.iterdir()
                  if p.is_dir() and all((p / f).exists() for f in needed))


@st.cache_data
def load_tables(user):
    folder = DATA / user
    tables = {}
    for name, filename in TABLES.items():
        df = pd.read_csv(folder / filename)
        for col in ID_COLS:
            if col in df.columns:
                df[col] = df[col].astype("Int64")
        tables[name] = df
    for name, filename in SUMMARIES.items():
        tables[name] = pd.read_csv(folder / filename).iloc[0].to_dict()
    return tables


def display_name(user):
    """The profile's display name, falling back to the username."""
    name = load_tables(user)["profile"].get("display_name")
    return name.strip() if isinstance(name, str) and name.strip() else user


def possessive(name):
    """'Rohan' -> "Rohan's", 'James' -> "James'"."""
    return f"{name}'" if name.endswith("s") else f"{name}'s"


def current_tables():
    """Tables for whichever user is selected (set in app.py)."""
    return load_tables(st.session_state["user"])


@st.cache_data
def load_reviews(user):
    """The user's own review text by film_key (latest viewing), or {} if unavailable.

    Interim files are never committed, so a deployed app never has them.
    """
    viewings = Path(__file__).resolve().parent.parent / "data" / "interim" / user / "viewings.csv"
    if not viewings.exists():
        return {}
    v = pd.read_csv(viewings, usecols=["film_key", "watched_date", "review_clean"])
    v = v[v["review_clean"].fillna("").str.strip() != ""].sort_values("watched_date")
    return v.drop_duplicates("film_key", keep="last").set_index("film_key")["review_clean"].to_dict()
