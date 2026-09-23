"""Deck versions of the charts from 03, in the app's palette on its dark background.

    python make_slide_charts.py

Saves PNGs to assets/slides/. The notebook keeps its own light versions: these exist so
the slides and the app look like the same project.
"""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.paths import ROOT, interim_dir

DARK, SURFACE, SLATE, MUTED = "#15181d", "#2c3440", "#445466", "#98aabb"
WHITE, ORANGE, GREEN, BLUE = "#ffffff", "#ff8000", "#00e054", "#40bcf4"

OUT = ROOT / "assets" / "slides"
OUT.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({
    "figure.facecolor": DARK, "axes.facecolor": DARK, "savefig.facecolor": DARK,
    "text.color": WHITE, "axes.labelcolor": MUTED, "axes.edgecolor": SLATE,
    "xtick.color": MUTED, "ytick.color": MUTED, "grid.color": SLATE,
    "font.size": 13, "axes.titlesize": 15, "axes.labelsize": 13,
    "figure.dpi": 200,
})

df = pd.read_csv(interim_dir() / "modelling_base.csv", parse_dates=["watched_date"])
df["crowd_5"]    = df["vote_average"] / 2
df["divergence"] = df["rating"] - df["crowd_5"]


def save(fig, name):
    for ax in fig.axes:
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT / name, bbox_inches="tight")
    plt.close(fig)
    print(f"saved {OUT / name}")


# ---------- 1. my rating vs the crowd score ----------

rng = np.random.default_rng(0)
jitter = rng.uniform(-0.11, 0.11, len(df))

fig, ax = plt.subplots(figsize=(8, 5.5))
ax.scatter(df["crowd_5"], df["rating"] + jitter,
           c=np.where(df["divergence"] >= 0, GREEN, BLUE),
           alpha=0.55, s=20, linewidths=0)

lims = [df["crowd_5"].min() - 0.15, df["crowd_5"].max() + 0.15]
ax.plot(lims, lims, "--", color=MUTED, linewidth=1.2, label="agreement with the crowd")
m, b = np.polyfit(df["crowd_5"], df["rating"], 1)
ax.plot(np.array(lims), m * np.array(lims) + b, color=ORANGE, linewidth=2.2, label="trend")

ax.set_xlim(lims)
ax.set_ylim(0.3, 5.3)
ax.set_xlabel("TMDB crowd score (rescaled to 0–5)")
ax.set_ylabel("My rating")
ax.grid(alpha=0.15)
leg = ax.legend(frameon=False, loc="upper left")
for text in leg.get_texts():
    text.set_color(MUTED)
save(fig, "rating_vs_crowd.png")


# ---------- 2. review length by rating (a null result) ----------

ratings = sorted(df["rating"].unique())
groups  = [df.loc[df["rating"] == r, "review_words"].values for r in ratings]

fig, ax = plt.subplots(figsize=(8, 4.5))
bp = ax.boxplot(groups, tick_labels=[f"{r}" for r in ratings], showfliers=False,
                patch_artist=True, medianprops={"color": ORANGE, "linewidth": 2})
for patch in bp["boxes"]:
    patch.set(facecolor=SURFACE, edgecolor=SLATE)
for part in ("whiskers", "caps"):
    for line in bp[part]:
        line.set_color(SLATE)

ax.set_xlabel("My rating")
ax.set_ylabel("Review length (words)")
ax.grid(alpha=0.15, axis="y")
save(fig, "review_length_by_rating.png")