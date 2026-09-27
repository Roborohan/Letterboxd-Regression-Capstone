"""Letterboxd export loading — moved from 01_data_loading.ipynb."""

import io
import re
import zipfile
from pathlib import Path, PurePosixPath

import pandas as pd

REQUIRED_FILES = ["diary.csv", "ratings.csv"]
OPTIONAL_FILES = ["reviews.csv", "watchlist.csv", "watched.csv", "profile.csv"]


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


MAX_EXPORT_BYTES = 100_000_000       # uncompressed; a real export is a few MB


def load_export_zip(data, max_bytes=MAX_EXPORT_BYTES):
    """The same dict as load_export, read from an export .zip held in memory — nothing on disk.

    Letterboxd's zip has the main CSVs at the top and more copies in subfolders (deleted/,
    orphaned/...), so each file is taken from the shallowest level it appears at.
    """
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise ValueError("That isn't a zip file. Upload the .zip Letterboxd emails you, unopened.")
    with z:
        if sum(i.file_size for i in z.infolist()) > max_bytes:
            raise ValueError("That zip is far larger than a Letterboxd export.")
        found = {}
        for info in z.infolist():
            path = PurePosixPath(info.filename)
            if path.suffix == ".csv" and path.name in REQUIRED_FILES + OPTIONAL_FILES:
                if path.name not in found or len(path.parts) < len(found[path.name].parts):
                    found[path.name] = path
        missing = [f for f in REQUIRED_FILES if f not in found]
        if missing:
            raise ValueError("This doesn't look like a Letterboxd export — it has no "
                             + " or ".join(missing) + ".")
        return {name.replace(".csv", ""): pd.read_csv(z.open(str(path)))
                for name, path in found.items()}


def film_key(df, title_col="Name", year_col="Year"):
    return df[title_col].str.strip() + " (" + df[year_col].astype("Int64").astype(str) + ")"


def display_name(profile):
    """Name to show in the app: Given Name if it is set, otherwise the Username; None without a profile."""
    if profile is None or profile.empty:
        return None
    row = profile.iloc[0]
    for col in ("Given Name", "Username"):
        value = row.get(col)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def user_slug(profile):
    """Folder name for this export's app tables: the Username, lower-case and filesystem-safe."""
    username = None if profile is None or profile.empty else profile.iloc[0].get("Username")
    if not isinstance(username, str) or not username.strip():
        return "default"
    return re.sub(r"[^a-z0-9_-]", "", username.strip().lower()) or "default"


# Letterboxd's Location is free text; these cover the common forms, and anything
# unrecognised falls back to no region (worldwide release dates) rather than a guess.
REGIONS = {
    "united kingdom": "GB", "uk": "GB", "england": "GB", "scotland": "GB", "wales": "GB",
    "northern ireland": "GB", "united states": "US", "usa": "US", "us": "US",
    "america": "US", "canada": "CA", "ireland": "IE", "australia": "AU",
    "new zealand": "NZ", "india": "IN", "germany": "DE", "france": "FR", "spain": "ES",
    "italy": "IT", "netherlands": "NL", "sweden": "SE", "norway": "NO", "denmark": "DK",
    "finland": "FI", "japan": "JP", "south korea": "KR", "korea": "KR", "brazil": "BR",
    "mexico": "MX", "philippines": "PH", "singapore": "SG", "south africa": "ZA",
}


def region_from_profile(profile):
    """A TMDB region code from the profile's Location, or None if it isn't recognised."""
    if profile is None or profile.empty:
        return None
    location = profile.iloc[0].get("Location")
    if not isinstance(location, str) or not location.strip():
        return None
    parts = [p.strip().lower().strip(".") for p in location.split(",")]
    for part in reversed(parts):                      # the country is usually last
        if part in REGIONS:
            return REGIONS[part]
    return None