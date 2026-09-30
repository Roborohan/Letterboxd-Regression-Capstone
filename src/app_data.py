"""App data loading.

Two kinds of viewer, loaded the same way:
  a folder      data/processed/<username>/, written by the notebooks or run_pipeline.py —
                the examples everyone sees
  an upload     "run:<id>", the same files held in Firestore (see src/store.py) — seen only
                by the browser that uploaded it, or someone with its private link
"""

import io
import json
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
APP_FILES = list(TABLES.values()) + list(SUMMARIES.values()) + ["reviews.csv", "providers.json"]
OPTIONAL_FILES = {"reviews.csv", "providers.json"}      # an older upload may not have them
RUN_PREFIX = "run:"


def is_run(user):
    return isinstance(user, str) and user.startswith(RUN_PREFIX)


def run_id(user):
    return user[len(RUN_PREFIX):]

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


@st.cache_data(ttl=3600, show_spinner="Loading your films…")
def run_files(rid):
    """An uploaded run's files, {filename: bytes}, from Firestore. Cleared when a run is deleted."""
    from src import store
    return store.load_files(rid)


def viewer_files(user):
    """{filename: bytes} for any viewer: a folder's files, or an upload's."""
    if is_run(user):
        return run_files(run_id(user))
    folder = DATA / user
    return {f: (folder / f).read_bytes() for f in APP_FILES if (folder / f).exists()}


def tables_from_files(files):
    """The app's tables from its files, however they were stored."""
    tables = {}
    for name, filename in TABLES.items():
        df = pd.read_csv(io.BytesIO(files[filename]))
        for col in ID_COLS:
            if col in df.columns:
                df[col] = df[col].astype("Int64")
        tables[name] = df
    for name, filename in SUMMARIES.items():
        tables[name] = pd.read_csv(io.BytesIO(files[filename])).iloc[0].to_dict()
    return tables


@st.cache_data
def load_tables(user):
    return tables_from_files(viewer_files(user))


# ---------- Where films are streaming ----------

REGION_NAMES = {
    "GB": "the UK", "US": "the US", "IE": "Ireland", "CA": "Canada", "AU": "Australia",
    "NZ": "New Zealand", "IN": "India", "DE": "Germany", "FR": "France", "ES": "Spain",
    "IT": "Italy", "NL": "the Netherlands", "SE": "Sweden", "NO": "Norway", "DK": "Denmark",
    "FI": "Finland", "JP": "Japan", "KR": "South Korea", "BR": "Brazil", "MX": "Mexico",
    "PH": "the Philippines", "SG": "Singapore", "ZA": "South Africa", "BE": "Belgium",
    "AT": "Austria", "CH": "Switzerland", "PT": "Portugal", "PL": "Poland", "AR": "Argentina",
}


@st.cache_data(show_spinner=False)
def _parse_providers(user, stamp):
    data = viewer_files(user).get("providers.json")
    return json.loads(data) if data else None


def load_providers(user):
    """A viewer's streaming availability ({as_of, providers, films}), or None if they have none.

    Keyed on the file's modification time, so when the weekly refresh updates an example's file,
    the app picks it up without a restart. Uploads come through run_files, cached for an hour.
    """
    path = DATA / user / "providers.json"
    stamp = path.stat().st_mtime if not is_run(user) and path.exists() else None
    return _parse_providers(user, stamp)


def visitor_region(fallback=None):
    """The visitor's country, from their browser's language setting ('en-GB' -> 'GB').

    A best guess — a browser set to US English in London says US — so the Filters menu lets it
    be changed. Falls back to `fallback`, then the UK.
    """
    locale = (st.context.locale or "").replace("_", "-")
    region = locale.split("-")[-1].upper() if "-" in locale else None
    if region in REGION_NAMES:
        return region
    return fallback if fallback in REGION_NAMES else "GB"


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
    """Review text by film_key, latest viewing of each film.

    Locally this reads the full interim data; a deployed copy has only the published subset
    (the films that can appear as a neighbour), written by the pipeline. Either way the app
    shows the same thing — reviews explain a prediction and are never a model input.
    """
    local = Path(__file__).resolve().parent.parent / "data" / "interim" / user / "viewings.csv"
    if not is_run(user) and local.exists():
        v = pd.read_csv(local, usecols=["film_key", "watched_date", "review_clean"])
        v = v.sort_values("watched_date").drop_duplicates("film_key", keep="last")
    else:
        published = viewer_files(user).get("reviews.csv")
        if published is None:
            return {}
        v = pd.read_csv(io.BytesIO(published))
    v = v[v["review_clean"].fillna("").str.strip() != ""]
    return v.set_index("film_key")["review_clean"].to_dict()
