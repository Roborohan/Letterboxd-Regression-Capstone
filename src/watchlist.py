"""Watchlist prediction — moved from 05_watchlist.ipynb.

Everything after TMDB matching: which films get a prediction, the final fit on every
rated viewing, the flags, the gap against the crowd-based estimate, and the rated films
behind each prediction. The notebook keeps the exploration; the pipeline calls these.
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression

from src.features import (PLAIN_NUMERIC, LOG_NUMERIC, HISTORY_KEYS,
                          build_features_F, build_features_H,
                          keyword_scores, add_keyword_score)
from src.tmdb import sensitive_poster

import json
from pathlib import Path

from src.tmdb import discover_upcoming, fetch_all_details

MAX_SHORT    = 40      # Academy definition of a short, in minutes
WINDOW_DAYS  = 90      # how far ahead coming soon looks
N_NEIGHBOURS = 5
RANGE_COLS   = ["runtime", "vote_average", "vote_count", "popularity"]
LOG_DEPLOY   = [c for c in LOG_NUMERIC if c != "review_words"]


def select_films(wl, rated_films, prediction_date, min_votes=None):
    """Split matched watchlist films into ones to predict and unreleased coming-soon candidates.

    `min_votes` defaults to the lowest vote count among the rated films: below that, TMDB's
    crowd score is outside anything the model has seen.
    """
    wl = wl.copy()
    wl["release_date"] = pd.to_datetime(wl["release_date"], errors="coerce")
    if min_votes is None:
        min_votes = int(rated_films["vote_count"].min())

    rated_lo, rated_hi = rated_films[RANGE_COLS].min(), rated_films[RANGE_COLS].max()

    few_votes = wl["vote_count"] < min_votes
    short     = ~few_votes & (wl["runtime"] <= MAX_SHORT)

    upcoming = wl[few_votes
                  & (wl["release_date"] > prediction_date)
                  & (wl["release_date"] <= prediction_date + pd.Timedelta(days=WINDOW_DAYS))
                  & (wl["runtime"] > 0)].copy()

    wl_pred = wl[~few_votes & ~short].copy()
    out = (wl_pred[RANGE_COLS] < rated_lo) | (wl_pred[RANGE_COLS] > rated_hi)
    wl_pred["out_of_range"] = out.apply(lambda row: "|".join(row.index[row]), axis=1)

    return wl_pred, upcoming


def watchlist_features(rated_df, rows, genres, languages):
    """Features for the rated films (fit) and for `rows` (predict), built on the same frame.

    History for the new rows is computed over the combined frame, so each unrated row sees
    the full rated history and adds nothing to it.
    """
    n = len(rated_df)
    new_rows  = rows.assign(rating=np.nan, film_decade=(rows["film_year"] // 10) * 10)
    combined  = pd.concat([rated_df, new_rows], ignore_index=True)

    F_all   = build_features_F(combined, genres, languages, PLAIN_NUMERIC, LOG_DEPLOY)
    H_rated = build_features_H(rated_df, genres, HISTORY_KEYS)
    H_comb  = build_features_H(combined, genres, HISTORY_KEYS)
    kw_oof, kw_new = keyword_scores(rated_df, new_rows)

    X_fit = add_keyword_score(pd.concat([F_all[:n], H_rated], axis=1), kw_oof)
    X_new = add_keyword_score(pd.concat([F_all[n:], H_comb[n:]], axis=1).reset_index(drop=True),
                              kw_new)
    return X_fit, X_new


def _add_flag(series, flag):
    return series.apply(lambda s: flag if s == "" else s + "|" + flag)


def predict_watchlist(rated_df, rated_films, wl_pred, X_fit, X_wl, params):
    """Fit on every rated viewing and predict the watchlist, with flags and the crowd gap."""
    final_rf = RandomForestRegressor(**params).fit(X_fit, rated_df["rating"])

    wl_out = wl_pred.reset_index(drop=True).copy()
    wl_out["pred"] = final_rf.predict(X_wl)

    genre_cols = [c for c in X_wl.columns if c.startswith("genre_")]
    no_genre = (X_wl[genre_cols].sum(axis=1) == 0).values
    wl_out.loc[no_genre, "out_of_range"] = _add_flag(wl_out.loc[no_genre, "out_of_range"], "genre")

    yr_lo, yr_hi = rated_df["film_year"].min(), rated_df["film_year"].max()
    off_year = (wl_out["film_year"] < yr_lo) | (wl_out["film_year"] > yr_hi)
    wl_out.loc[off_year, "out_of_range"] = _add_flag(wl_out.loc[off_year, "out_of_range"], "film_year")

    crowd_model = LinearRegression().fit(rated_df[["vote_average"]], rated_df["rating"])
    wl_out["crowd_pred"] = crowd_model.predict(wl_out[["vote_average"]])
    wl_out["gap"] = wl_out["pred"] - wl_out["crowd_pred"]

    crowd_lo, crowd_hi = rated_films["vote_average"].quantile([0.025, 0.975])
    wl_out.loc[~wl_out["vote_average"].between(crowd_lo, crowd_hi), "gap"] = np.nan

    wl_out["sensitive_poster"] = sensitive_poster(wl_out["keywords"])

    ranges = {"crowd_lo": crowd_lo, "crowd_hi": crowd_hi,
              "film_year_min": yr_lo, "film_year_max": yr_hi}
    return wl_out, final_rf, ranges


def neighbour_table(final_rf, X_fit, X_wl, rated_df, wl_out, n_neighbours=N_NEIGHBOURS):
    """The rated films behind each prediction, by random-forest leaf weight."""
    leaves_fit = final_rf.apply(X_fit)
    leaves_wl  = final_rf.apply(X_wl)
    n_trees    = leaves_fit.shape[1]

    weight = np.zeros((len(X_wl), len(X_fit)), dtype=np.float32)
    for t in range(n_trees):
        sizes = np.bincount(leaves_fit[:, t])
        weight += (leaves_wl[:, [t]] == leaves_fit[:, t]) / sizes[leaves_fit[:, t]]
    weight /= n_trees

    codes, film_keys = pd.factorize(rated_df["film_key"])
    W = np.zeros((len(X_wl), len(film_keys)), dtype=np.float32)
    for j, c in enumerate(codes):
        W[:, c] += weight[:, j]

    films = (rated_df.drop_duplicates("film_key", keep="last")
             .set_index("film_key").loc[film_keys]
             .rename_axis("film_key").reset_index())

    top = np.argsort(-W, axis=1)[:, :n_neighbours]
    neighbours = pd.DataFrame([
        {"film_uri": wl_out.at[i, "film_uri"], "rank": r + 1,
         "neighbour_key": films.at[j, "film_key"], "neighbour_title": films.at[j, "film_title"],
         "neighbour_year": films.at[j, "film_year"], "neighbour_rating": films.at[j, "rating"],
         "neighbour_tmdb_id": films.at[j, "tmdb_id"], "neighbour_poster": films.at[j, "poster_path"],
         "share": W[i, j]}
        for i, js in enumerate(top) for r, j in enumerate(js)
    ])
    neighbours["neighbour_sensitive"] = neighbours["neighbour_key"].map(
        sensitive_poster(films.set_index("film_key")["keywords"]))
    return neighbours

CROWD_COLS = ["vote_average", "log_vote_count", "log_popularity"]


def popular_releases(prediction_date, *, headers, cache_dir, region="GB", pages=2,
                     known_ids=(), top_n=20):
    """The most popular films opening in `region` in the window, excluding films already known.

    Both TMDB calls are cached per region and prediction date, so a re-run costs nothing.
    """
    cache_dir = Path(cache_dir)
    start = (prediction_date + pd.Timedelta(days=1)).date().isoformat()
    end   = (prediction_date + pd.Timedelta(days=WINDOW_DAYS)).date().isoformat()

    discover_cache = cache_dir / f"upcoming_discover_{region}_{prediction_date.date()}.json"
    if discover_cache.exists():
        discovered = json.loads(discover_cache.read_text())
    else:
        discovered = discover_upcoming(start, end, headers=headers, pages=pages, region=region)
        cache_dir.mkdir(parents=True, exist_ok=True)
        discover_cache.write_text(json.dumps(discovered))

    known = set(known_ids)
    popular = list({d["id"]: d for d in discovered if d["id"] not in known}.values())
    popular = [d for d in popular if (d.get("release_date") or "") >= start]   # already in cinemas

    details = fetch_all_details([d["id"] for d in popular], headers=headers,
                                cache_path=cache_dir / f"upcoming_details_{region}_"
                                                       f"{prediction_date.date()}.json")
    details["popularity_rank"] = range(1, len(details) + 1)
    details["uk_release"] = [d["release_date"] for d in popular]

    long_enough = details["runtime"] > MAX_SHORT       # also excludes runtime 0: not known yet
    return details[long_enough].head(top_n).copy(), details


def coming_soon_table(rated_df, upcoming, popular_top, genres, languages, X_fit, params):
    """Predictions for unreleased films, from the no-crowd model: no crowd score exists yet."""
    cs_wl = upcoming.assign(source="watchlist",
                            release_shown=upcoming["release_date"].dt.date.astype(str))
    cs_pop = popular_top.assign(source="popular",
                                film_title=popular_top["tmdb_title"],
                                film_year=pd.to_datetime(popular_top["release_date"]).dt.year,
                                film_uri=None,
                                release_shown=popular_top["uk_release"])
    cs_pop["film_key"] = cs_pop["film_title"] + " (" + cs_pop["film_year"].astype(str) + ")"

    cs = pd.concat([cs_wl, cs_pop], ignore_index=True)
    _, X_cs = watchlist_features(rated_df, cs, genres, languages)
    X_cs     = X_cs.drop(columns=CROWD_COLS)
    X_fit_nc = X_fit.drop(columns=CROWD_COLS)
    assert list(X_cs.columns) == list(X_fit_nc.columns)

    nocrowd_rf = RandomForestRegressor(**params).fit(X_fit_nc, rated_df["rating"])
    cs["pred"] = nocrowd_rf.predict(X_cs)

    rng_cols = ["runtime", "film_year"]
    off = (cs[rng_cols] < rated_df[rng_cols].min()) | (cs[rng_cols] > rated_df[rng_cols].max())
    off["genre"] = X_cs[[c for c in X_cs.columns if c.startswith("genre_")]].sum(axis=1).values == 0
    cs["out_of_range"] = off.apply(lambda r: "|".join(r.index[r]), axis=1)
    cs["sensitive_poster"] = sensitive_poster(cs["keywords"])

    return cs.sort_values(["source", "pred"], ascending=[False, False])