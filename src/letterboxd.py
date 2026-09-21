"""Letterboxd export loading — moved from 01_data_loading.ipynb."""

from pathlib import Path

import pandas as pd

REQUIRED_FILES = ["diary.csv", "reviews.csv", "ratings.csv"]
OPTIONAL_FILES = ["watchlist.csv", "watched.csv"]


def load_export(export_dir):
    """Load a Letterboxd export directory into a dict of dataframes."""
    export_dir = Path(export_dir or "")

    if not export_dir.is_dir():
        raise FileNotFoundError(
            f"Export directory not found: {export_dir!s}\n"
            "Set LETTERBOXD_EXPORT_DIR in your .env, or pass export_dir explicitly."
        )

    missing = [f for f in REQUIRED_FILES if not (export_dir / f).exists()]
    if missing:
        raise FileNotFoundError(f"Export is missing required files: {missing}")

    data = {f.replace(".csv", ""): pd.read_csv(export_dir / f) for f in REQUIRED_FILES}

    for f in OPTIONAL_FILES:
        if (export_dir / f).exists():
            data[f.replace(".csv", "")] = pd.read_csv(export_dir / f)

    return data


def film_key(df, title_col="Name", year_col="Year"):
    return df[title_col].str.strip() + " (" + df[year_col].astype("Int64").astype(str) + ")"