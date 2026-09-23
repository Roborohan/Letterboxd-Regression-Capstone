"""Modelling helpers — moved from 04_models.ipynb.

The notebook keeps the full exploration; this module holds the pieces the pipeline
re-runs for any export, so both use the same code and the same defaults.
"""

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import GridSearchCV, TimeSeriesSplit

from src.features import (PLAIN_NUMERIC, LOG_NUMERIC, HISTORY_KEYS,
                          genre_vocabulary, top_n_vocabulary, build_features_F,
                          build_features_H, keyword_scores, add_keyword_score)
from src.tmdb import sensitive_poster

CV_SPLITS = 5

RIDGE_GRID = {"ridge__alpha": [0.1, 1, 10, 100, 1000]}
RF_GRID = {
    "min_samples_leaf": [1, 5, 15, 30],
    "max_features":     ["sqrt", 0.5, 1.0],
}


def tune(estimator, grid, X, y, cv=None, verbose=True):
    """Grid search over time-ordered folds; returns the refitted best model."""
    search = GridSearchCV(estimator, grid, cv=cv or TimeSeriesSplit(n_splits=CV_SPLITS),
                          scoring="neg_mean_absolute_error", n_jobs=-1)
    search.fit(X, y)
    if verbose:
        print(f"  best {search.best_params_}  CV MAE {-search.best_score_:.3f}")
    return search.best_estimator_


def bootstrap_mae_diff(y_true, pred_a, pred_b, n_boot=2000, seed=0):
    """MAE(a) - MAE(b) on the test set, with a 95% CI from resampling the same films for both."""
    y_true = np.asarray(y_true)
    err_a = np.abs(y_true - np.asarray(pred_a))
    err_b = np.abs(y_true - np.asarray(pred_b))
    rng = np.random.default_rng(seed)

    n = len(y_true)
    diffs = np.empty(n_boot)
    for i in range(n_boot):
        idx = rng.integers(0, n, n)
        diffs[i] = err_a[idx].mean() - err_b[idx].mean()

    return err_a.mean() - err_b.mean(), np.percentile(diffs, [2.5, 97.5])


def bootstrap_spearman_diff(y, a, b, n_boot=2000, seed=0):
    """Spearman(y, a) - Spearman(y, b) on the test set, with a 95% CI from resampling the same films."""
    y, a, b = map(np.asarray, (y, a, b))
    rng = np.random.default_rng(seed)
    n = len(y)
    diffs = np.empty(n_boot)
    for i in range(n_boot):
        idx = rng.integers(0, n, n)
        diffs[i] = spearmanr(y[idx], a[idx])[0] - spearmanr(y[idx], b[idx])[0]
    return spearmanr(y, a)[0] - spearmanr(y, b)[0], np.percentile(diffs, [2.5, 97.5])


TEST_FRACTION = 0.2
N_TREES       = 300
CROWD_COLS    = ["vote_average", "log_vote_count", "log_popularity"]


def build_ladder(df, test_fraction=TEST_FRACTION, verbose=True):
    """Every model the app needs, fitted exactly as 04 fits them.

    Returns (train, test, preds, parts): `preds` holds the test-set predictions for each
    rung and the no-crowd variant; `parts` holds the vocabularies and feature frames the
    watchlist run needs.
    """
    df = df.sort_values("watched_date").reset_index(drop=True)
    split_idx = int(len(df) * (1 - test_fraction))
    train, test = df[:split_idx].copy(), df[split_idx:].copy()
    y_train = train["rating"]

    genres    = genre_vocabulary(train["genres"])
    languages = top_n_vocabulary(train["original_language"], n=10)

    F_all = build_features_F(df, genres, languages, PLAIN_NUMERIC, LOG_NUMERIC)
    H_all = build_features_H(df, genres, HISTORY_KEYS)
    X3_all = pd.concat([F_all, H_all], axis=1)

    X2_train, X2_test = F_all[:split_idx], F_all[split_idx:]
    X3_train, X3_test = X3_all[:split_idx], X3_all[split_idx:]

    kw_oof, kw_test = keyword_scores(train, test)
    X4_train = add_keyword_score(X3_train, kw_oof)
    X4_test  = add_keyword_score(X3_test,  kw_test)

    X4d_train = X4_train.drop(columns=["log_review_words"])     # deployable: no review length
    X4d_test  = X4_test.drop(columns=["log_review_words"])
    X4n_train = X4d_train.drop(columns=CROWD_COLS)              # no-crowd, for unreleased films
    X4n_test  = X4d_test.drop(columns=CROWD_COLS)

    def rf(X):
        return tune(RandomForestRegressor(n_estimators=N_TREES, random_state=0),
                    RF_GRID, X, y_train, verbose=verbose)

    if verbose:
        print("Model 2 — film metadata")
    rf_2 = rf(X2_train)
    if verbose:
        print("Model 3 — + viewing history")
    rf_3 = rf(X3_train)
    if verbose:
        print("Model 4 — + keywords, no review length (deployable)")
    rf_4d = rf(X4d_train)
    if verbose:
        print("Model 4 — no-crowd variant")
    rf_4n = rf(X4n_train)

    crowd_model = LinearRegression().fit(train[["vote_average"]], y_train)

    preds = {
        "pred_m0":     np.full(len(test), y_train.median()),
        "pred_m1":     crowd_model.predict(test[["vote_average"]]),
        "pred_m2":     rf_2.predict(X2_test),
        "pred_m3":     rf_3.predict(X3_test),
        "pred_deploy": rf_4d.predict(X4d_test),
        "pred_nocrowd": rf_4n.predict(X4n_test),
    }
    parts = {"genres": genres, "languages": languages, "split_idx": split_idx,
             "X4d_train": X4d_train, "X4d_test": X4d_test,
             "models": {"m2": rf_2, "m3": rf_3, "deploy": rf_4d, "nocrowd": rf_4n,
                        "crowd": crowd_model}}
    return train, test, preds, parts


LADDER_COLS = ["pred_m0", "pred_m1", "pred_m2", "pred_m3", "pred_deploy"]

TEST_OUT_COLS = ["film_key", "film_title", "film_year", "watched_date", "rating",
                 "vote_average", "vote_count", "tmdb_id", "poster_path"]


def test_table(test, preds):
    """The app's test_predictions table: the held-out films with every rung's prediction."""
    return (test[TEST_OUT_COLS].reset_index(drop=True)
            .assign(**{c: preds[c] for c in LADDER_COLS},
                    sensitive_poster=sensitive_poster(test["keywords"]).values))


def model_summary(df, train, test, preds):
    """One row holding every model figure the app quotes."""
    y = test["rating"].values
    gain, (gain_lo, gain_hi) = bootstrap_mae_diff(y, preds["pred_m1"], preds["pred_deploy"])
    rho_model, _ = spearmanr(y, preds["pred_deploy"])
    rho_crowd, _ = spearmanr(y, test["vote_average"])
    rho_diff, (rho_lo, rho_hi) = bootstrap_spearman_diff(y, preds["pred_deploy"],
                                                         test["vote_average"].values)
    return pd.DataFrame([{
        "n_rated":        len(df),
        "n_train":        len(train),
        "n_test":         len(test),
        "first_watched":  df["watched_date"].min().date().isoformat(),
        "last_watched":   df["watched_date"].max().date().isoformat(),
        "median_rating":  float(np.median(preds["pred_m0"])),
        **{f"mae_{c.removeprefix('pred_')}": np.abs(y - preds[c]).mean() for c in LADDER_COLS},
        "mae_nocrowd":    np.abs(y - preds["pred_nocrowd"]).mean(),
        "gain_vs_crowd":  gain,
        "gain_ci_lo":     gain_lo,
        "gain_ci_hi":     gain_hi,
        "spearman_model": rho_model,
        "spearman_crowd": rho_crowd,
        "spearman_diff":  rho_diff,
        "spearman_ci_lo": rho_lo,
        "spearman_ci_hi": rho_hi,
    }])