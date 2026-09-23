"""Run the whole pipeline on one Letterboxd export.

    python run_pipeline.py [--export path/to/letterboxd-export] [--date YYYY-MM-DD]
                           [--region US] [--name "Their Name"]

With no arguments it uses the one letterboxd-* folder in the project root, or
LETTERBOXD_EXPORT_DIR from .env, and takes the display name and cinema region from the
export's profile. The flags are there for when the profile doesn't say.

Writes the app's files to data/processed/<username>/ and the working files to
data/interim/<username>/, so several people's exports can sit side by side.

The notebooks (01-05) remain the record of the analysis for the export they were run on.
This repeats the same steps, from the same code in src/, for any export — with one
difference it prints loudly: TMDB matches that need a human eye are dropped rather than
reviewed by hand.
"""

import argparse
import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from src.features import genre_vocabulary, top_n_vocabulary
from src.letterboxd import (display_name, film_key, load_export, region_from_profile,
                            user_slug)
from src.modelling import build_ladder, model_summary, test_table
from src.paths import CACHE, app_dir, interim_dir, set_active_user
from src.prepare import build_modelling_base, build_viewings, match_and_enrich
from src.tmdb import make_headers
from src.watchlist import (WINDOW_DAYS, coming_soon_table, neighbour_table,
                           popular_releases, predict_watchlist, select_films,
                           watchlist_features)

MIN_FILMS = 300       # below this the test set is too small for the comparison to mean anything


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
    p.add_argument("--min-films", type=int, default=MIN_FILMS,
                   help=f"minimum rated diary entries (default: {MIN_FILMS})")
    return p.parse_args()


def step(text):
    print(f"\n=== {text}", flush=True)


def main():
    args = parse_args()
    load_dotenv(".env")
    token = os.getenv("TMDB_TOKEN")
    if not token:
        sys.exit("TMDB_TOKEN is not set. Put it in .env before running.")
    headers = make_headers(token)

    export_dir = args.export or os.getenv("LETTERBOXD_EXPORT_DIR")
    if not args.export:
        found = [p for p in Path(".").glob("letterboxd-*") if p.is_dir()]
        if len(found) == 1:                     # one export sitting here: use it
            export_dir = str(found[0])
        elif len(found) > 1:
            sys.exit("More than one export folder here — pass --export:\n  "
                     + "\n  ".join(str(p) for p in found))
    if not export_dir:
        sys.exit("No export found. Put the export folder here, pass --export, "
                 "or set LETTERBOXD_EXPORT_DIR in .env.")
    date = pd.Timestamp(args.date) if args.date else pd.Timestamp.today().normalize()

    # ---------- the export ----------
    step("Loading the export")
    export  = load_export(export_dir)
    profile = export.get("profile")
    user    = set_active_user(user_slug(profile))
    INTERIM, APP = interim_dir(user), app_dir(user)
    name = (args.name or os.getenv(f"DISPLAY_NAME_{user.upper()}")
            or display_name(profile) or user)
    region = args.region or region_from_profile(profile)
    print(f"user: {user}   display name: {name}   region: {region or 'worldwide'}")

    viewings = build_viewings(export)
    if len(viewings) < args.min_films:
        sys.exit(f"\nOnly {len(viewings)} rated diary entries. Below about {args.min_films} the "
                 f"held-out test set is too small for the comparison against the crowd score to "
                 f"say anything either way, so this export is not worth running.")
    print(f"{len(viewings)} rated viewings, "
          f"{viewings['watched_date'].min().date()} to {viewings['watched_date'].max().date()}")
    viewings.to_csv(INTERIM / "viewings.csv", index=False)
    pd.DataFrame({"username": [user], "display_name": [name]}).to_csv(APP / "profile.csv", index=False)

    # ---------- TMDB ----------
    step("Matching rated films to TMDB")
    unique = (viewings.drop_duplicates("film_key")[["film_key", "film_title", "film_year"]]
              .reset_index(drop=True))
    films, dropped = match_and_enrich(unique, headers=headers, cache_dir=CACHE, prefix="tmdb")
    print(f"matched {len(films)} of {len(unique)} films; dropped {len(dropped)} needing review")
    films.to_csv(INTERIM / "films_enriched.csv", index=False)

    rated_df = build_modelling_base(viewings, films)
    rated_df.to_csv(INTERIM / "modelling_base.csv", index=False)
    print(f"modelling base: {len(rated_df)} viewings of {rated_df['film_key'].nunique()} films")

    # ---------- the models ----------
    step("Fitting the model ladder (this is the slow part)")
    train, test, preds, parts = build_ladder(rated_df)
    test_table(test, preds).to_csv(APP / "test_predictions.csv", index=False)
    summary = model_summary(rated_df, train, test, preds)
    summary.to_csv(APP / "model_summary.csv", index=False)

    s = summary.iloc[0]
    print(f"\ntest MAE: crowd {s['mae_m1']:.3f} -> model {s['mae_deploy']:.3f}")
    print(f"gain over the crowd score: {s['gain_vs_crowd']:+.3f} "
          f"[{s['gain_ci_lo']:+.3f}, {s['gain_ci_hi']:+.3f}] stars")
    print(f"Spearman: crowd {s['spearman_crowd']:.3f} -> model {s['spearman_model']:.3f}")
    if s["gain_ci_lo"] <= 0:
        print("note: the interval includes zero — this model does not beat the crowd score here.")

    # ---------- the watchlist ----------
    if "watchlist" not in export:
        print("\nNo watchlist.csv in the export — skipping the watchlist and coming-soon tables.")
        return

    step("Matching the watchlist to TMDB")
    watchlist = export["watchlist"].copy()
    watchlist["film_key"] = film_key(watchlist)
    keep = watchlist["film_key"].notna() & ~watchlist["film_key"].duplicated(keep=False)
    films_wl = (watchlist[keep]
                .rename(columns={"Name": "film_title", "Year": "film_year",
                                 "Letterboxd URI": "film_uri"})
                [["film_key", "film_title", "film_year", "film_uri"]]
                .reset_index(drop=True))
    print(f"{len(films_wl)} of {len(watchlist)} watchlist films can be matched "
          f"({(~keep).sum()} have no year or a duplicate title+year)")

    wl_matched, wl_dropped = match_and_enrich(films_wl, headers=headers, cache_dir=CACHE,
                                              prefix="watchlist")
    wl = wl_matched.merge(films_wl[["film_key", "film_uri"]], on="film_key", how="left")
    print(f"matched {len(wl)}; dropped {len(wl_dropped)} needing review")
    wl.to_csv(INTERIM / "watchlist_matched.csv", index=False)

    step("Predicting the watchlist")
    genres    = genre_vocabulary(rated_df["genres"])
    languages = top_n_vocabulary(rated_df["original_language"], n=10)
    wl_pred, upcoming = select_films(wl, films, date)
    X_fit, X_wl = watchlist_features(rated_df, wl_pred, genres, languages)

    deploy_params  = parts["models"]["deploy"].get_params()
    nocrowd_params = parts["models"]["nocrowd"].get_params()
    wl_out, final_rf, ranges = predict_watchlist(rated_df, films, wl_pred, X_fit, X_wl, deploy_params)

    OUT_COLS = ["film_uri", "film_key", "film_title", "film_year", "tmdb_id",
            "pred", "crowd_pred", "gap", "vote_average", "vote_count", "runtime", "genres",
            "overview", "director", "original_language", "release_date", "poster_path",
            "out_of_range", "sensitive_poster"]
    (wl_out[OUT_COLS].sort_values("pred", ascending=False)
     .to_csv(APP / "watchlist_predictions.csv", index=False))
    print(f"{len(wl_out)} films predicted, {wl_out['gap'].notna().sum()} with a crowd gap, "
          f"{(wl_out['out_of_range'] != '').sum()} flagged")

    neighbours = neighbour_table(final_rf, X_fit, X_wl, rated_df, wl_out)
    neighbours.to_csv(APP / "neighbours.csv", index=False)

    step(f"Coming soon ({region or 'worldwide'}, {WINDOW_DAYS} days from {date.date()})")
    known = set(wl["tmdb_id"].dropna().astype(int)) | set(films["tmdb_id"].dropna().astype(int))
    popular_top, all_upcoming = popular_releases(date, headers=headers, cache_dir=CACHE,
                                                 region=region, known_ids=known)
    cs = coming_soon_table(rated_df, upcoming, popular_top, genres, languages, X_fit, nocrowd_params)
    CS_COLS = ["source", "film_uri", "film_key", "film_title", "film_year", "tmdb_id", "pred",
            "release_shown", "runtime", "genres", "overview", "director", "original_language",
            "poster_path", "out_of_range", "sensitive_poster"]
    cs[CS_COLS].to_csv(APP / "coming_soon.csv", index=False)
    print(f"{(cs['source'] == 'watchlist').sum()} from the watchlist, "
          f"{(cs['source'] == 'popular').sum()} popular releases")

    # films left out of coming soon because TMDB has no runtime yet
    in_window = (wl["release_date"].pipe(pd.to_datetime, errors="coerce").between(
        date, date + pd.Timedelta(days=WINDOW_DAYS), inclusive="right"))
    no_runtime = pd.concat([
        wl.loc[in_window & (wl["runtime"].fillna(0) <= 0), "tmdb_title"],
        all_upcoming.loc[all_upcoming["runtime"].fillna(0) <= 0, "tmdb_title"],
    ]).sort_values()

    recent_from = (date.year // 10) * 10
    pd.DataFrame([{
        "prediction_date":    date.date().isoformat(),
        "region":             region,
        "n_watchlist":        len(watchlist),
        "n_predicted":        len(wl_out),
        "n_with_gap":         int(wl_out["gap"].notna().sum()),
        "rated_mean":         rated_df["rating"].mean(),
        "crowd_lo":           ranges["crowd_lo"],
        "crowd_hi":           ranges["crowd_hi"],
        "rated_median_votes": rated_df.drop_duplicates("film_key")["vote_count"].median(),
        "rated_votes_p75":    rated_df.drop_duplicates("film_key")["vote_count"].quantile(0.75),
        **{f"{c}_min": films[c].min() for c in ["runtime", "vote_average", "vote_count", "popularity"]},
        **{f"{c}_max": films[c].max() for c in ["runtime", "vote_average", "vote_count", "popularity"]},
        "film_year_min":      ranges["film_year_min"],
        "film_year_max":      ranges["film_year_max"],
        "genre_vocab":        "|".join(genres),
        "recent_from":        recent_from,
        "recent_mean":        rated_df.loc[rated_df["film_year"] >= recent_from, "rating"].mean(),
        "n_coming_watchlist": int((cs["source"] == "watchlist").sum()),
        "n_coming_popular":   int((cs["source"] == "popular").sum()),
        "no_runtime_yet":     "|".join(no_runtime),
    }]).to_csv(APP / "watchlist_summary.csv", index=False)

    step("Done")
    print(f"app files written to {APP}")
    print("start the app with:  streamlit run app.py")


if __name__ == "__main__":
    main()
