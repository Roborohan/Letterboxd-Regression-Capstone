# Beyond the Crowd Score

**Can a model learn what one person likes, beyond what everyone else likes?**

**[Try it →](https://beyond-the-crowd-score.streamlit.app/)** *(hosted on Streamlit Community
Cloud — if it's been idle, it takes about 30 seconds to wake)*

Film ratings sites answer "is this good?" with a crowd average. This project asks a
narrower question: given one viewer's rating history, can a model predict *their* rating
better than the crowd score can — and can it say why?

Built from a Letterboxd export (1,192 rated viewings, Dec 2021 – Aug 2026), enriched with
TMDB metadata, and presented as a Streamlit app. A Data & AI capstone project.

**Built with** Python · pandas · scikit-learn (Random Forest, Ridge) · Streamlit · the TMDB API

---

## What it found

Tested on the 239 most recent films, held out chronologically and never seen in training:

| | Crowd score | Model |
|---|---|---|
| Mean absolute error | 0.656 ★ | **0.545 ★** |
| Spearman rank correlation | 0.340 | **0.612** |

The improvement over the crowd score is **+0.111 ★, 95% CI [0.059, 0.166]** — an interval
clear of zero, so not an artefact of which films happened to fall in the test set. For
comparison, the crowd score itself beats "guess the same rating every time" by only 0.026 ★,
which is not significant.

Two honest caveats the app states plainly:

- **Predictions are compressed.** They span roughly 2.2–4.6 ★ against a real range of
  0.5–5.0 ★, so the model is better at ordering films than at calling extremes.
- **Film metadata does most of the work.** Viewing history adds a small, statistically
  uncertain improvement at this sample size, and review text produced no usable feature
  at all. Both null results are reported rather than buried.

### Does it work for anyone else?

Two friends exported their data, and the same pipeline ran on both with no code changes and
nothing tuned by hand. The answers differed:

| | Films | Gain over the crowd score | Ranks films better than the crowd? |
|---|---|---|---|
| Me | 1,192 | **+0.111 ★** [+0.059, +0.166] | Yes — 0.612 vs 0.340 |
| Friend 1 | 897 | +0.006 ★ [−0.015, +0.027] | Yes — 0.313 vs 0.238 |
| Friend 2 | 426 | +0.052 ★ [−0.008, +0.108] | Yes — 0.603 vs 0.580 |

One viewer agrees with the crowd more than I do, leaving less room to beat it; the other's gain
is a useful size, but 86 test films can't resolve it. Three people, three different answers —
which is the point: the pipeline travels, the finding is one person's.

---

## The app

Five pages. The first four show the example viewers from precomputed tables; the fifth builds
the same thing from your own Letterboxd export.

1. **Intro** — the question, the data, and what each layer of the model knows.
2. **Beyond the crowd** — the 12 best-known held-out films, chosen by TMDB vote count alone.
   Open one and step through the model layer by layer, watching the prediction move towards
   (or away from) the actual rating.
3. **Watchlist** — 3,924 unseen films with predicted ratings, sorted by likely favourites,
   likely misses, or the biggest gap above or below the crowd-based estimate. Open a film
   for the rated films the prediction drew on.
4. **Coming soon** — unreleased films, predicted by a variant that never sees a crowd score.
5. **Your films** — upload your own export and the whole pipeline runs on it, in the
   background. See below.

A selector switches between viewers, and a settings menu can turn off the blur on explicit
posters, show predictions unrounded, or reduce motion. Strong language in quoted review excerpts
is always masked. Every film links to its Letterboxd page, every prediction has a shareable link,
and the watchlist can be searched and filtered by genre, decade and length. It works on phones as
well as desktop.

### Upload your own export

Download your data from Letterboxd (**Settings → Data → Export your data**) and upload the zip on
the **Your films** page. The same pipeline the project uses runs on it — TMDB matching, the full
model ladder with its test against the crowd score, the watchlist and coming soon — and every page
of the app then works with your films. You need at least 300 rated diary entries and a watchlist.

- **It runs in the background**, with progress and a carousel of your own posters while you wait:
  usually 3–6 minutes, less when other people have uploaded the same films. You can close the page
  and come back.
- **Your results stay yours.** Only the browser you uploaded from sees them, or anyone you give the
  private link to. The download bundles every result into one file, which can be uploaded again to
  restore them instantly.
- **Nothing is kept longer than it needs to be.** The export is read in memory and never stored; the
  results are deleted 90 days after they were last viewed, or immediately from the page.

---

## How it works

| | |
|---|---|
| **01** `data_loading` | Builds one row per rated viewing from the export; cleans review text. |
| **02** `tmdb_enrichment` | Matches each film to TMDB and pulls metadata; caches every API response. |
| **03** `eda` | Joins the two, establishes baselines, writes the modelling base. |
| **04** `models` | The model ladder: constant → crowd score → film metadata → viewing history → keywords. Chronological 80/20 split, time-ordered CV, paired bootstrap intervals. |
| **05** `watchlist` | Refits the chosen model on every rated viewing and predicts the watchlist, the crowd gap, and the films behind each prediction. |

The notebooks are the record of the analysis and the decisions behind it. The reusable
code lives in `src/`, and `src/pipeline.py` runs every step on any export. It's used two ways:

- **`run_pipeline.py`**, from the command line: local caches, results written to
  `data/processed/<username>/`.
- **The app's uploads** (`src/runner.py`): a background worker takes one upload at a time, runs the
  same pipeline against a TMDB cache shared by every upload, and saves the results to Firestore
  (`src/store.py`). Because the film data is shared, each upload only looks up the films nobody
  has uploaded before.

---

## Running it

```bash
conda create -n py313 python=3.13 && conda activate py313
pip install -r requirements-dev.txt     # to run the app only: pip install -r requirements.txt
```

Create `.env` in the project root:

```
TMDB_TOKEN=your_tmdb_v4_read_access_token
LETTERBOXD_EXPORT_DIR=/path/to/letterboxd-export
DISPLAY_NAME_YOURUSERNAME=Your Name      # optional, overrides the export's profile
```

Then either run the pipeline:

```bash
python run_pipeline.py                   # or --export path/to/export --region US
streamlit run app.py
```

or work through the notebooks 01 → 05 and start the app the same way.

`run_pipeline.py` derives the username, display name and cinema region from the export's
profile, and stops with a clear message below ~300 rated diary entries, where the held-out
test set is too small for the comparison to say anything either way. It differs from the
notebooks in one respect it prints: TMDB matches that need a human eye are dropped rather
than reviewed by hand, which on this export costs 8 films and about 0.003 ★ of the headline.

Several people's exports can sit side by side — each gets its own folder, and the app shows a
selector when there is more than one. Set `DEFAULT_USER=<username>` in `.env` to choose who it
opens on.

The notebooks always work on whichever export ran last, so `02`–`05` stop with a clear message
if that isn't the user they were written for.

### Uploads (optional)

The app runs without any of this; only the **Your films** page needs it, and it says so if it's
missing. Uploads keep their results in [Firestore](https://firebase.google.com/docs/firestore) on
the free Spark plan. Create a Firebase project with a Firestore database, generate a service account
key (Project settings → Service accounts), and add it to `.streamlit/secrets.toml`, which is
gitignored:

```toml
[firestore]
type = "service_account"
project_id = "your-project-id"
private_key = "-----BEGIN PRIVATE KEY-----\n…\n-----END PRIVATE KEY-----\n"
client_email = "…"
# …the rest of the key file's fields, one per line
```

When deploying, the same `[firestore]` block and `TMDB_TOKEN` go in the host's secrets instead.
Expired results are deleted by the app itself every few hours; Firestore's own automatic deletion
would need billing enabled, which the project avoids so that it can never incur charges.

---

## Data and privacy

- **Committed:** the app's tables in `data/processed/<username>/` — titles, ratings,
  predictions, summary figures, and the review excerpts the app can quote (only for films that
  can appear as a neighbour of a prediction).
- **Not committed:** the export itself, the working files in `data/interim/` (including the
  full review history), and the TMDB API caches.
- Reviews are shown to explain a prediction and are **never a model input**. To keep them off a
  deployed copy, delete `data/processed/<username>/reviews.csv` — the app simply omits them.
- Deploying publicly makes any committed user's ratings and watchlist public. Get their
  agreement first.
- **Uploads:** the export is read in memory and never written anywhere. Only the app's result
  tables are kept, in Firestore (London), under a long random id that works as a private link; a
  cookie remembers which results belong to a browser and holds nothing else. Results are deleted 90
  days after they were last viewed, or immediately on request.

---

## Limitations

One viewer, 1,192 viewings — three, counting the portability check. Everything here is a case
study, not a claim about viewers in general. The watchlist is a pool the viewer already chose, so predictions are "how much will
you like this film you picked", not "will you like a random film". Low ratings are rare,
extremes are hardest to predict, and TMDB's crowd fields are read as they are today rather
than as they were when each film was watched.

---

## Credits

Ratings, reviews and watchlists come from personal [Letterboxd](https://letterboxd.com/) data
exports, used with each person's permission. This is an independent project, not affiliated with,
endorsed by or sponsored by Letterboxd; "Letterboxd" and its logo are trademarks of Letterboxd
Limited.

Film data and posters from [TMDB](https://www.themoviedb.org/). This product uses the TMDB API but
is not endorsed or certified by TMDB.
