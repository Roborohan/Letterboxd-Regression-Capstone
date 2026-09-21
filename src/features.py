"""Feature building — moved from 04_models.ipynb.

Vocabularies and column lists are passed in rather than read from notebook
globals, so the same code builds features for any training set (the 953-film
split in 04, all 1,192 rated viewings in 05) and for the watchlist.
"""

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import Ridge
from sklearn.model_selection import TimeSeriesSplit


# ---------- Definitions shared by 04 and 05 ----------

PLAIN_NUMERIC = ["vote_average", "film_year"]
LOG_NUMERIC   = ["runtime", "vote_count", "popularity", "review_words"]

HISTORY_KEYS = {
    "director":          "dir",
    "cinematographer":   "dop",
    "original_language": "lang",
    "film_decade":       "decade",
}


# ---------- Block F: film metadata ----------

def genre_vocabulary(series, min_count=20):
    counts = (series.fillna("").str.split("|").explode()
              .replace("", np.nan).dropna().value_counts())
    return sorted(counts[counts >= min_count].index)


def top_n_vocabulary(series, n=10, min_count=15):
    """Most frequent values in the training data, above a minimum count."""
    counts = series.dropna().value_counts()
    return sorted(counts[counts >= min_count].head(n).index)


def encode_genres(series, vocab):
    """One binary column per genre in the vocabulary."""
    split = series.fillna("").str.split("|")
    return pd.DataFrame(
        {f"genre_{g}": split.apply(lambda gs: int(g in gs)) for g in vocab},
        index=series.index,
    )


def encode_categorical(series, vocab, prefix):
    """One binary column per vocabulary value, plus an 'other' catch-all."""
    out = pd.DataFrame(
        {f"{prefix}_{v}": (series == v).astype(int) for v in vocab},
        index=series.index,
    )
    out[f"{prefix}_other"] = (~series.isin(vocab)).astype(int)
    return out


def encode_numeric(frame, plain_cols, log_cols):
    out = frame[plain_cols].copy()
    for col in log_cols:
        out[f"log_{col}"] = np.log1p(frame[col])
    return out


def build_features_F(frame, genres, languages, plain_cols, log_cols):
    """Block F — film metadata only."""
    return pd.concat([
        encode_numeric(frame, plain_cols, log_cols),
        encode_genres(frame["genres"], genres),
        encode_categorical(frame["original_language"], languages, "lang"),
        frame[["in_collection"]].astype(int),
    ], axis=1)


# ---------- Block H: personal history ----------

def expanding_group_mean(frame, key_col, value_col="rating"):
    """Mean of value_col over strictly-earlier rows sharing the same key."""
    return (frame.groupby(key_col)[value_col]
                 .transform(lambda s: s.shift(1).expanding().mean()))


def expanding_group_count(frame, key_col, value_col="rating"):
    """Number of strictly-earlier rows sharing the same key."""
    return (frame.groupby(key_col)[value_col]
                 .transform(lambda s: s.shift(1).expanding().count()))


def genre_history(frame, vocab):
    """Mean of prior ratings across this film's genres, and total prior exposure."""
    totals = {g: 0.0 for g in vocab}
    counts = {g: 0 for g in vocab}
    means, exposure = [], []

    for genres_str, rating in zip(frame["genres"].fillna(""), frame["rating"]):
        gs = [g for g in genres_str.split("|") if g in vocab]

        seen = [g for g in gs if counts[g] > 0]
        means.append(np.mean([totals[g] / counts[g] for g in seen]) if seen else np.nan)
        exposure.append(sum(counts[g] for g in gs))

        for g in gs:                      # update AFTER recording, never before
            totals[g] += rating
            counts[g] += 1

    return pd.Series(means, index=frame.index), pd.Series(exposure, index=frame.index)


def impute_history(H, prefixes):
    """Fill missing group means with the running overall mean at that point in time."""
    out = H.copy()

    out["hist_mean_all_missing"] = out["hist_mean_all"].isna().astype(int)
    out["hist_mean_all"] = out["hist_mean_all"].fillna(out["hist_mean_all"].median())

    fallback = out["hist_mean_all"]
    for prefix in prefixes:
        mean_col, n_col = f"hist_mean_{prefix}", f"hist_n_{prefix}"
        out[f"{mean_col}_missing"] = out[mean_col].isna().astype(int)
        out[mean_col] = out[mean_col].fillna(fallback)
        out[n_col] = out[n_col].fillna(0)

    return out


def build_features_H(frame, genres, history_keys):
    """Block H — personal history, expanding window over strictly earlier films."""
    out = pd.DataFrame(index=frame.index)

    out["hist_mean_all"]  = frame["rating"].shift(1).expanding().mean()
    out["hist_count_all"] = frame["rating"].shift(1).expanding().count()

    for col, prefix in history_keys.items():
        out[f"hist_mean_{prefix}"] = expanding_group_mean(frame, col)
        out[f"hist_n_{prefix}"]    = expanding_group_count(frame, col)

    g_mean, g_exposure = genre_history(frame, genres)
    out["hist_mean_genre"] = g_mean
    out["hist_n_genre"]    = g_exposure

    return impute_history(out, list(history_keys.values()) + ["genre"])


# ---------- Keyword score ----------

def make_kw_vec():
    return TfidfVectorizer(tokenizer=lambda s: [k for k in s.split("|") if k],
                           token_pattern=None, lowercase=False, min_df=5)


def keyword_scores(train_df, test_df, alpha=3, n_splits=10):
    """Stacked keyword score: expanding-window out-of-fold for train, full-fit for test."""
    kw_tr = train_df["keywords"].fillna("").values
    kw_te = test_df["keywords"].fillna("").values
    y = train_df["rating"].values

    oof = np.full(len(kw_tr), np.nan)
    for fit_idx, val_idx in TimeSeriesSplit(n_splits=n_splits).split(kw_tr):
        vec = make_kw_vec()
        m = Ridge(alpha=alpha).fit(vec.fit_transform(kw_tr[fit_idx]), y[fit_idx])
        oof[val_idx] = m.predict(vec.transform(kw_tr[val_idx]))

    vec = make_kw_vec()
    m = Ridge(alpha=alpha).fit(vec.fit_transform(kw_tr), y)
    return oof, m.predict(vec.transform(kw_te))


def add_keyword_score(X3, scores):
    X = X3.copy()
    X["kw_score_missing"] = np.isnan(scores).astype(int)
    X["kw_score"] = np.where(np.isnan(scores), X3["hist_mean_all"].values, scores)
    return X
