"""The pipeline itself: one Letterboxd export in, the app's files out.

Used two ways, from the same code:
  run_pipeline.py   the command line — local JSON caches, writes data/processed/ and data/interim/
  src/runner.py     the app's uploads — the shared Firestore cache, results saved to Firestore

`run` does no file writing of its own: it returns the app's files as bytes and the working
tables as dataframes, and the caller decides where they go.
"""

import json

import pandas as pd

from src.features import genre_vocabulary, top_n_vocabulary
from src.letterboxd import display_name, film_key, region_from_profile, user_slug
from src.modelling import build_ladder, model_summary, test_table
from src.prepare import build_modelling_base, build_viewings, match_and_enrich
from src.tmdb import fetch_all_providers
from src.watchlist import (WINDOW_DAYS, coming_soon_table, neighbour_table,
                           popular_releases, predict_watchlist, select_films,
                           watchlist_features)

MIN_FILMS = 300       # below this the test set is too small for the comparison to mean anything

OUT_COLS = ["film_uri", "film_key", "film_title", "film_year", "tmdb_id",
            "pred", "crowd_pred", "gap", "vote_average", "vote_count", "runtime", "genres",
            "overview", "director", "original_language", "release_date", "poster_path",
            "out_of_range", "sensitive_poster"]

CS_COLS = ["source", "film_uri", "film_key", "film_title", "film_year", "tmdb_id", "pred",
           "release_shown", "runtime", "genres", "overview", "director",
           "original_language", "poster_path", "out_of_range", "sensitive_poster"]

# How far through the run each stage starts, for the progress bar. The model fitting and the
# TMDB lookups dominate; everything else is quick.
STAGES = {
    "export":    (0.00, 0.02, "Reading your export"),
    "rated":     (0.02, 0.30, "Matching your rated films to TMDB"),
    "models":    (0.30, 0.72, "Fitting the models — the slow part"),
    "watchlist": (0.72, 0.88, "Matching your watchlist to TMDB"),
    "predict":   (0.88, 0.92, "Predicting your watchlist"),
    "streaming": (0.92, 0.96, "Checking where your watchlist is streaming"),
    "coming":    (0.96, 0.99, "Finding films coming soon"),
}


class PipelineError(Exception):
    """A problem with the export itself, worded for the person whose export it is."""


def csv_bytes(df):
    return df.to_csv(index=False).encode()


def identify(export, *, name=None, region=None, tag=None):
    """Username, display name and cinema region from the export's profile, unless given."""
    profile = export.get("profile")
    user = user_slug(profile) + (f"-{tag}" if tag else "")
    return (user,
            name or display_name(profile) or user,
            region or region_from_profile(profile))


def run(export, *, headers, date, user, name, region, cache_dir=None, stores=None,
        min_films=MIN_FILMS, log=print, progress=None, on_matched=None):
    """Run every step on a loaded export.

    Caches are either local (`cache_dir`) or shared (`stores`, see store.shared_caches).
    `progress(fraction, stage, detail)` is called as the run moves on, if given, and
    `on_matched(films)` once the rated films have their TMDB details (the app uses it to show
    the person's own posters while they wait).

    Returns (app_files, interim): {filename: bytes} for data/processed/<user>/, and
    {name: DataFrame} of the working tables for data/interim/<user>/.
    """
    def report(stage, within=0.0, detail=""):
        if progress:
            lo, hi, label = STAGES[stage]
            progress(lo + (hi - lo) * within, label, detail)

    def within(stage):
        return lambda f: report(stage, f)

    cache = {"stores": stores} if stores is not None else {"cache_dir": cache_dir}
    app, interim = {}, {}

    # ---------- the export ----------
    report("export")
    viewings = build_viewings(export)
    if len(viewings) < min_films:
        raise PipelineError(
            f"Your export has {len(viewings)} rated diary entries. Below about {min_films}, the "
            f"films held back for testing are too few for the comparison against the crowd "
            f"score to say anything either way, so it isn't worth running yet.")
    log(f"{len(viewings)} rated viewings, "
        f"{viewings['watched_date'].min().date()} to {viewings['watched_date'].max().date()}")
    interim["viewings"] = viewings
    profile_row = pd.DataFrame({"username": [user], "display_name": [name],
                                "n_rated_entries": [len(viewings)]})   # before TMDB matching
    app["profile.csv"] = csv_bytes(profile_row)
    interim["profile"] = profile_row

    # ---------- TMDB ----------
    report("rated")
    unique = (viewings.drop_duplicates("film_key")[["film_key", "film_title", "film_year"]]
              .reset_index(drop=True))
    films, dropped = match_and_enrich(unique, headers=headers, prefix="tmdb",
                                      progress=within("rated"), **cache)
    log(f"matched {len(films)} of {len(unique)} films; dropped {len(dropped)} needing review")
    interim["films_enriched"] = films
    if on_matched:
        on_matched(films)

    rated_df = build_modelling_base(viewings, films)
    interim["modelling_base"] = rated_df
    log(f"modelling base: {len(rated_df)} viewings of {rated_df['film_key'].nunique()} films")
    if len(rated_df) < min_films:
        raise PipelineError(
            f"Only {len(rated_df)} of your rated viewings could be matched to TMDB with "
            f"confidence, which is below the {min_films} the comparison needs.")

    # ---------- the models ----------
    report("models")
    train, test, preds, parts = build_ladder(rated_df, verbose=log is print,
                                             progress=within("models"))
    app["test_predictions.csv"] = csv_bytes(test_table(test, preds))
    summary = model_summary(rated_df, train, test, preds)
    app["model_summary.csv"] = csv_bytes(summary)

    s = summary.iloc[0]
    log(f"\ntest MAE: crowd {s['mae_m1']:.3f} -> model {s['mae_deploy']:.3f}")
    log(f"gain over the crowd score: {s['gain_vs_crowd']:+.3f} "
        f"[{s['gain_ci_lo']:+.3f}, {s['gain_ci_hi']:+.3f}] stars")
    log(f"Spearman: crowd {s['spearman_crowd']:.3f} -> model {s['spearman_model']:.3f}")
    if s["gain_ci_lo"] <= 0:
        log("note: the interval includes zero — this model does not beat the crowd score here.")

    # ---------- the watchlist ----------
    if "watchlist" not in export:
        log("\nNo watchlist.csv in the export — skipping the watchlist and coming-soon tables.")
        return app, interim

    report("watchlist")
    watchlist = export["watchlist"].copy()
    watchlist["film_key"] = film_key(watchlist)
    keep = watchlist["film_key"].notna() & ~watchlist["film_key"].duplicated(keep=False)
    films_wl = (watchlist[keep]
                .rename(columns={"Name": "film_title", "Year": "film_year",
                                 "Letterboxd URI": "film_uri"})
                [["film_key", "film_title", "film_year", "film_uri"]]
                .reset_index(drop=True))
    log(f"{len(films_wl)} of {len(watchlist)} watchlist films can be matched "
        f"({(~keep).sum()} have no year or a duplicate title+year)")

    wl_matched, wl_dropped = match_and_enrich(films_wl, headers=headers, prefix="watchlist",
                                              progress=within("watchlist"), **cache)
    wl = wl_matched.merge(films_wl[["film_key", "film_uri"]], on="film_key", how="left")
    log(f"matched {len(wl)}; dropped {len(wl_dropped)} needing review")
    interim["watchlist_matched"] = wl

    report("predict")
    genres    = genre_vocabulary(rated_df["genres"])
    languages = top_n_vocabulary(rated_df["original_language"], n=10)
    wl_pred, upcoming = select_films(wl, films, date)
    if wl_pred.empty:
        raise PipelineError("None of your watchlist films could be matched to TMDB with "
                            "enough information to predict them.")
    X_fit, X_wl = watchlist_features(rated_df, wl_pred, genres, languages)

    deploy_params  = parts["models"]["deploy"].get_params()
    nocrowd_params = parts["models"]["nocrowd"].get_params()
    wl_out, final_rf, ranges = predict_watchlist(rated_df, films, wl_pred, X_fit, X_wl, deploy_params)
    app["watchlist_predictions.csv"] = csv_bytes(wl_out[OUT_COLS].sort_values("pred", ascending=False))
    log(f"{len(wl_out)} films predicted, {wl_out['gap'].notna().sum()} with a crowd gap, "
        f"{(wl_out['out_of_range'] != '').sum()} flagged")
    report("predict", 0.5)

    neighbours = neighbour_table(final_rf, X_fit, X_wl, rated_df, wl_out)
    app["neighbours.csv"] = csv_bytes(neighbours)

    # Review text for the films that can actually appear in the app: only a film shown as one of
    # a prediction's neighbours is ever quoted, so nothing else is published.
    shown   = set(neighbours["neighbour_key"])
    reviews = (viewings[viewings["film_key"].isin(shown)]
               .sort_values("watched_date")
               .drop_duplicates("film_key", keep="last")[["film_key", "review_clean"]])
    reviews = reviews[reviews["review_clean"].fillna("").str.strip() != ""]
    app["reviews.csv"] = csv_bytes(reviews)
    log(f"{len(reviews)} reviews published for the app "
        f"(of {len(shown)} films that can appear as a neighbour)")

    # Where each watchlist film is streaming, in every supported region. A nice extra, never a
    # reason to fail a run: if TMDB's streaming data can't be had, the run finishes without it.
    report("streaming")
    try:
        streaming = fetch_all_providers(
            wl_out["tmdb_id"], headers=headers, today=date,
            store=stores.get("providers") if stores is not None else None,
            progress=lambda done, total: report("streaming", done / total))
        app["providers.json"] = json.dumps(streaming).encode()
        log(f"streaming availability for {len(streaming['films'])} watchlist films")
    except Exception as e:                                   # noqa: BLE001 — optional extra
        log(f"streaming availability skipped: {e}")

    report("coming")
    known = set(wl["tmdb_id"].dropna().astype(int)) | set(films["tmdb_id"].dropna().astype(int))
    popular_top, all_upcoming = popular_releases(date, headers=headers, region=region,
                                                 known_ids=known, **cache)
    cs = coming_soon_table(rated_df, upcoming, popular_top, genres, languages, X_fit, nocrowd_params)
    app["coming_soon.csv"] = csv_bytes(cs[CS_COLS])
    log(f"{(cs['source'] == 'watchlist').sum()} from the watchlist, "
        f"{(cs['source'] == 'popular').sum()} popular releases")

    # films left out of coming soon because TMDB has no runtime yet
    in_window = (wl["release_date"].pipe(pd.to_datetime, errors="coerce").between(
        date, date + pd.Timedelta(days=WINDOW_DAYS), inclusive="right"))
    unreleased = wl["vote_count"] < int(films["vote_count"].min())   # as in select_films
    no_runtime = pd.concat([
        wl.loc[unreleased & in_window & (wl["runtime"].fillna(0) <= 0), "tmdb_title"],
        all_upcoming.loc[all_upcoming["runtime"].fillna(0) <= 0, "tmdb_title"],
    ]).sort_values()

    recent_from = (date.year // 10) * 10
    app["watchlist_summary.csv"] = csv_bytes(pd.DataFrame([{
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
    }]))
    report("coming", 1.0)
    return app, interim
