"""Building the working tables — moved from 01, 02 and 03.

The notebooks keep the checks and the commentary; these are the steps a pipeline run
repeats for any export: the viewings spine, TMDB matching under the automatic policy,
and the modelling base the models are fitted on.
"""

import html
import re

import pandas as pd

from src.letterboxd import film_key
from src.tmdb import AUTO_ACCEPT, fetch_all_details, match_all

TAG_RE   = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")
SMART = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"',
                       "\u201d": '"', "\u2013": "-", "\u2014": "-", "\u2026": "..."})

RENAME = {"Name": "film_title", "Year": "film_year", "Letterboxd URI": "entry_uri",
          "Rating": "rating", "Date": "logged_date", "Watched Date": "watched_date",
          "Review": "review_raw", "Rewatch": "is_rewatch"}


def clean_review(text):
    """Unescape entities, strip tags to spaces, straighten quotes, collapse whitespace."""
    if not isinstance(text, str):
        return ""
    text = html.unescape(text)
    text = TAG_RE.sub(" ", text)
    text = text.translate(SMART)
    return SPACE_RE.sub(" ", text).strip()


def build_viewings(export):
    """One row per rated viewing, in watched order — the spine 01 writes."""
    spine = export["diary"].merge(export["reviews"][["Letterboxd URI", "Review"]],
                                  on="Letterboxd URI", how="left", validate="one_to_one")
    spine = spine.rename(columns=RENAME)
    spine["logged_date"]  = pd.to_datetime(spine["logged_date"])
    spine["watched_date"] = pd.to_datetime(spine["watched_date"])
    spine["is_rewatch"]   = spine["is_rewatch"].eq("Yes")
    spine["film_key"]     = film_key(spine, "film_title", "film_year")
    spine = spine.drop(columns=["Tags"])

    spine = spine[spine["rating"].notna()].copy()          # no target, no model
    spine["review_clean"] = spine["review_raw"].apply(clean_review)
    spine["review_words"] = spine["review_clean"].str.split().str.len()

    spine = spine.sort_values(["watched_date", "logged_date"]).reset_index(drop=True)
    spine["viewing_index"]     = range(1, len(spine) + 1)
    spine["film_viewing_seq"]  = spine.groupby("film_key").cumcount() + 1
    spine["film_decade"]       = (spine["film_year"] // 10) * 10
    spine["film_age_at_watch"] = spine["watched_date"].dt.year - spine["film_year"]
    return spine


def match_and_enrich(films, *, headers, cache_dir, prefix="tmdb"):
    """Match films to TMDB and attach their details, keeping only confident matches.

    The automatic policy: accept `exact` and `year_off`, drop everything else. The
    notebooks review the rest by hand for one export; a pipeline run cannot.
    """
    matches  = match_all(films, headers=headers, cache_path=cache_dir / f"{prefix}_search_raw.json")
    accepted = matches[matches["confidence"].isin(AUTO_ACCEPT) & matches["tmdb_id"].notna()].copy()
    dropped  = matches[~matches.index.isin(accepted.index)]

    details  = fetch_all_details(accepted["tmdb_id"], headers=headers,
                                 cache_path=cache_dir / f"{prefix}_details.json")
    enriched = accepted.drop(columns=["vote_count"]).merge(details, on="tmdb_id", how="left")
    return enriched, dropped


def build_modelling_base(viewings, films):
    """Viewings joined to their TMDB data, matched films only, in watched order."""
    df = viewings.merge(films, on="film_key", how="left", validate="many_to_one")
    df = df[df["tmdb_id"].notna()].copy()
    df = df.drop(columns=["film_title_y", "film_year_y"]).rename(
        columns={"film_title_x": "film_title", "film_year_x": "film_year"})
    return df.sort_values("watched_date").reset_index(drop=True)