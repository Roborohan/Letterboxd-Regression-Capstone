"""Refresh where the example viewers' watchlist films are streaming.

    python scripts/refresh_providers.py              # every viewer in data/processed/
    python scripts/refresh_providers.py roborohan    # just one

Rewrites data/processed/<username>/providers.json and touches nothing else: no models are
re-run. A GitHub Action (.github/workflows/refresh-streaming.yml) runs this every Monday and
commits the result, and Streamlit Cloud picks the change up on its own. Needs TMDB_TOKEN, from
.env locally or the environment (the Action takes it from the repository's secrets).

Streaming data is JustWatch's, through TMDB, and is credited wherever the app shows it.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # scripts/ -> project root, for src/

import json
import os
import sys

import pandas as pd
from dotenv import load_dotenv

from src.paths import PROCESSED
from src.tmdb import fetch_all_providers, make_headers


def main():
    load_dotenv(".env")
    token = os.getenv("TMDB_TOKEN")
    if not token:
        sys.exit("TMDB_TOKEN is not set. Put it in .env, or in the environment.")
    users = sys.argv[1:] or sorted(p.name for p in PROCESSED.iterdir()
                                   if (p / "watchlist_predictions.csv").exists())
    headers = make_headers(token)
    for user in users:
        wl = pd.read_csv(PROCESSED / user / "watchlist_predictions.csv", usecols=["tmdb_id"])
        data = fetch_all_providers(wl["tmdb_id"], headers=headers)
        (PROCESSED / user / "providers.json").write_text(json.dumps(data, separators=(",", ":")))
        print(f"{user}: {len(data['films']):,} of {len(wl):,} watchlist films on a subscription "
              f"service somewhere, as of {data['as_of']}")


if __name__ == "__main__":
    main()
