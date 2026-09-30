"""Run the whole pipeline on one Letterboxd export.

    python scripts/run_pipeline.py [--export path/to/letterboxd-export] [--date YYYY-MM-DD]
                           [--region US] [--name "Their Name"] [--tag test]

With no arguments it uses the one letterboxd-* folder in the project root, or
LETTERBOXD_EXPORT_DIR from .env, and takes the display name and cinema region from the
export's profile. The flags are there for when the profile doesn't say.

Writes the app's files to data/processed/<username>/ and the working files to
data/interim/<username>/, so several people's exports can sit side by side. A run
overwrites the working files the notebooks use for that user, so use --tag for a trial
run, or re-run 01-03 afterwards to restore a hand-reviewed dataset.

The notebooks (01-05) remain the record of the analysis for the export they were run on.
This repeats the same steps, from the same code in src/, for any export — with one
difference it prints loudly: TMDB matches that need a human eye are dropped rather than
reviewed by hand. The steps themselves live in src/pipeline.py, which the app's upload
page runs too.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # scripts/ -> project root, for src/

import argparse
import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from src.letterboxd import load_export
from src.paths import CACHE, app_dir, interim_dir, set_active_user
from src.pipeline import MIN_FILMS, WINDOW_DAYS, PipelineError, identify, run
from src.tmdb import make_headers


def parse_args():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--export", default=None,
                   help="path to an unzipped Letterboxd export "
                        "(default: LETTERBOXD_EXPORT_DIR from .env)")
    p.add_argument("--date", default=None,
                   help="prediction date for the watchlist and coming soon (default: today)")
    p.add_argument("--region", default=None,
                   help="cinema region for coming soon (default: from the profile's location)")
    p.add_argument("--name", default=None,
                   help="display name for the app (default: the export's profile)")
    p.add_argument("--tag", default=None,
                   help="suffix for the folder name, e.g. --tag test writes to "
                        "<username>-test/ instead of overwriting an existing run")
    p.add_argument("--min-films", type=int, default=MIN_FILMS,
                   help=f"minimum rated diary entries (default: {MIN_FILMS})")
    return p.parse_args()


def find_export(arg):
    """The export folder: --export, else the one letterboxd-* folder here, else .env."""
    if arg:
        return arg
    found = [p for p in Path(".").glob("letterboxd-*") if p.is_dir()]
    if len(found) == 1:                     # one export sitting here: use it
        return str(found[0])
    if len(found) > 1:
        sys.exit("More than one export folder here — pass --export:\n  "
                 + "\n  ".join(str(p) for p in found))
    export_dir = os.getenv("LETTERBOXD_EXPORT_DIR")
    if not export_dir:
        sys.exit("No export found. Put the export folder here, pass --export, "
                 "or set LETTERBOXD_EXPORT_DIR in .env.")
    return export_dir


def step(text):
    print(f"\n=== {text}", flush=True)


def main():
    args = parse_args()
    load_dotenv(".env")
    token = os.getenv("TMDB_TOKEN")
    if not token:
        sys.exit("TMDB_TOKEN is not set. Put it in .env before running.")

    export = load_export(find_export(args.export))
    user, _, _ = identify(export, tag=args.tag)
    user, name, region = identify(export, tag=args.tag, region=args.region,
                                  name=args.name or os.getenv(f"DISPLAY_NAME_{user.upper()}"))
    date = pd.Timestamp(args.date) if args.date else pd.Timestamp.today().normalize()

    set_active_user(user)
    INTERIM, APP = interim_dir(user), app_dir(user)
    print(f"user: {user}   display name: {name}   region: {region or 'worldwide'}")
    print(f"notebooks 02-05 will now read this user's files ({INTERIM})")
    print(f"coming soon: {region or 'worldwide'}, {WINDOW_DAYS} days from {date.date()}")

    last = [None]
    def progress(fraction, stage, detail):
        if stage != last[0]:
            step(stage)
            last[0] = stage

    try:
        app, interim = run(export, headers=make_headers(token), date=date, user=user, name=name,
                           region=region, cache_dir=CACHE, min_films=args.min_films,
                           progress=progress)
    except PipelineError as e:
        sys.exit(f"\n{e}")

    for filename, data in app.items():
        (APP / filename).write_bytes(data)
    for table, df in interim.items():
        df.to_csv(INTERIM / f"{table}.csv", index=False)

    step("Done")
    print(f"app files written to {APP}")
    print(f"working files in {INTERIM} — notebooks 02-05 read these, so re-run 01-03 "
          f"before using the notebooks on a hand-reviewed dataset")
    print("start the app with:  streamlit run app.py")


if __name__ == "__main__":
    main()
