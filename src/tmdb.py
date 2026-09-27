"""TMDB matching and details — moved from 02_tmdb_enrichment.ipynb.

Nothing here reads .env or hard-codes a cache location: the caller builds headers
with make_headers(token) and passes a cache in, so the same code serves any user's
export and any cache.

Two kinds of cache: a local JSON file of raw responses (`cache_path`, used from the
command line), or a shared store (`store`, used by the app's uploads) — any object with
get_many(keys) and put_many(items). The store keeps only what's used: the fields
best_match reads from a search, and the parsed record for a film.
"""

import json
import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd
import requests


# ---------- API access ----------

def make_headers(token):
    """Request headers for the TMDB v4 Read Access Token (Bearer), not the v3 api_key."""
    return {"Authorization": f"Bearer {token}", "accept": "application/json"}


def _get(url, *, params=None, headers, tries=4):
    """GET with retries: TMDB rate-limits (429) and has the odd server error or timeout."""
    for attempt in range(tries):
        last = attempt == tries - 1
        try:
            r = requests.get(url, params=params, headers=headers, timeout=15)
        except requests.RequestException:
            if last:
                raise
            time.sleep(2 ** attempt)
            continue
        if r.status_code == 429 or r.status_code >= 500:
            if last:
                r.raise_for_status()
            time.sleep(float(r.headers.get("Retry-After") or 2 ** attempt))
            continue
        r.raise_for_status()
        return r.json()


def search_film(title, year=None, *, headers):
    params = {"query": title, "include_adult": True}
    if year:
        params["year"] = year
    return _get("https://api.themoviedb.org/3/search/movie", params=params, headers=headers)["results"]


SEARCH_FIELDS = ("id", "title", "original_title", "release_date", "vote_count")


def trim_results(results):
    """Just the fields best_match reads, from the top ten results — what a shared store keeps."""
    return [{k: r.get(k) for k in SEARCH_FIELDS} for r in results[:10]]


# ---------- Title comparison ----------

def normalise(title):
    """Flatten a title for comparison: lowercase, no accents, no punctuation."""
    if not isinstance(title, str):
        return ""
    title = unicodedata.normalize("NFKD", title)
    title = "".join(c for c in title if not unicodedata.combining(c))
    title = title.casefold()
    title = re.sub(r"[^\w\s]", " ", title)
    return re.sub(r"\s+", " ", title).strip()


def similarity(a, b):
    return SequenceMatcher(None, normalise(a), normalise(b)).ratio()


def score_candidate(candidate, title, year):
    """Classify one TMDB search result against the Letterboxd title and year."""
    sim = max(similarity(title, candidate.get("title") or ""),
              similarity(title, candidate.get("original_title") or ""))

    release = candidate.get("release_date") or ""
    cand_year = int(release[:4]) if release[:4].isdigit() else None
    gap = None if (year is None or cand_year is None) else abs(cand_year - year)

    if sim >= 0.95 and gap == 0:
        return "exact", sim
    if sim >= 0.95 and gap == 1:
        return "year_off", sim
    if sim >= 0.85 and (gap is None or gap <= 1):
        return "close", sim
    return "weak", sim


# ---------- Choosing a match ----------

TIERS = ["exact", "year_off", "close", "weak"]
DEMOTE = {"exact": "close", "year_off": "close", "close": "weak", "weak": "weak"}
MIN_VOTE_SHARE = 0.05        # under 5% of the best-known rival's votes = implausible
AUTO_ACCEPT = {"exact", "year_off"}


def best_match(results, title, year):
    """Pick the strongest candidate, demoting implausibly obscure title collisions."""
    if not results:
        return None

    scored = []
    for c in results[:10]:
        tier, sim = score_candidate(c, title, year)
        scored.append({"tier": tier, "sim": sim,
                       "votes": c.get("vote_count") or 0, "raw": c})

    # among candidates whose title genuinely matches, how well-known is the best?
    plausible = [s["votes"] for s in scored if s["sim"] >= 0.85]
    max_votes = max(plausible) if plausible else 0

    for s in scored:
        if s["sim"] >= 0.85 and max_votes > 0 and s["votes"] < max_votes * MIN_VOTE_SHARE:
            s["tier"] = DEMOTE[s["tier"]]

    scored.sort(key=lambda s: (TIERS.index(s["tier"]), -s["sim"], -s["votes"]))
    best = scored[0]
    c = best["raw"]

    release = c.get("release_date") or ""
    return {
        "tmdb_id":       c.get("id"),
        "matched_title": c.get("title"),
        "matched_year":  int(release[:4]) if release[:4].isdigit() else None,
        "confidence":    best["tier"],
        "similarity":    round(best["sim"], 3),
        "vote_count":    c.get("vote_count"),
    }


WORKERS = 8          # lookups in flight at once — well inside TMDB's ~40 requests a second


def _lookup_many(keys, lookup, *, cache, progress, total, done_already):
    """Run `lookup(key)` for every uncached key, several at a time, storing each result in the
    cache as it arrives. Results are keyed, so the order they finish in doesn't matter."""
    done = done_already
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(lookup, k): k for k in keys}
        for n, future in enumerate(as_completed(futures), start=1):
            cache[futures[future]] = future.result()
            done += 1
            if n % 100 == 0:
                cache.flush()
                print(f"  {done}/{total} processed ({n} API calls)")
            if progress and (done % 20 == 0 or done == total):
                progress(done, total)
    return len(keys)


class _Cache:
    """One interface over both caches: a local JSON file of raw responses, or a shared store."""

    def __init__(self, keys, cache_path=None, store=None):
        self.path, self.store, self.pending = cache_path and Path(cache_path), store, {}
        if store is not None:
            self.data = store.get_many(keys)
        else:
            self.data = json.loads(self.path.read_text()) if self.path.exists() else {}

    def __contains__(self, key):
        return key in self.data

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        self.data[key] = value
        self.pending[key] = value

    def flush(self):
        if self.store is not None:
            if self.pending:
                self.store.put_many(self.pending)
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data))
        self.pending = {}


def match_all(films, *, headers, cache_path=None, store=None, progress=None, delay=None):
    """Match every film to TMDB, caching search responses. `progress(done, total)` is optional.

    Lookups run several at a time (WORKERS); `delay` is accepted for older callers and ignored.
    """
    cache = _Cache(list(films["film_key"]), cache_path, store)
    films = films.reset_index(drop=True)
    years = {f.film_key: (None if pd.isna(f.film_year) else int(f.film_year))
             for f in films.itertuples(index=False)}
    titles = dict(zip(films["film_key"], films["film_title"]))

    def lookup(key):
        results = search_film(titles[key], years[key], headers=headers)
        if not results:
            results = search_film(titles[key], headers=headers)          # year mismatch fallback
        return trim_results(results) if store is not None else results

    todo = list(dict.fromkeys(k for k in films["film_key"] if k not in cache))
    new_calls = _lookup_many(todo, lookup, cache=cache, progress=progress, total=len(films),
                             done_already=len(films) - len(todo))
    rows = []

    for film in films.itertuples(index=False):
        key, year = film.film_key, years[film.film_key]

        match = best_match(cache[key], film.film_title, year)
        if match is None:
            match = {"tmdb_id": None, "matched_title": None, "matched_year": None,
                     "confidence": "no_match", "similarity": 0.0, "vote_count": None}

        rows.append({"film_key": key, "film_title": film.film_title,
                     "film_year": film.film_year, **match})

    cache.flush()
    print(f"done — {new_calls} new API calls, {len(rows) - new_calls} from cache")
    return pd.DataFrame(rows)


# ---------- Film details ----------

def fetch_details(tmdb_id, *, headers):
    return _get(f"https://api.themoviedb.org/3/movie/{tmdb_id}",
                params={"append_to_response": "credits,keywords"}, headers=headers)


PARSED_COLUMNS = ("tmdb_id", "tmdb_title", "release_date", "runtime", "original_language",
                  "origin_country", "genres", "keywords", "overview", "vote_average", "vote_count",
                  "popularity", "in_collection", "collection_name", "director", "cinematographer",
                  "cast_top5", "poster_path")


def parse_details(d):
    """Flatten a TMDB detail response into a single flat record."""
    crew = d.get("credits", {}).get("crew", [])
    cast = d.get("credits", {}).get("cast", [])

    def first_with_job(job):
        for c in crew:
            if c.get("job") == job:
                return c.get("name")
        return None

    collection = d.get("belongs_to_collection")

    return {
        "tmdb_id":         d.get("id"),
        "tmdb_title":      d.get("title"),
        "release_date":    d.get("release_date"),
        "runtime":         d.get("runtime"),
        "original_language": d.get("original_language"),
        "origin_country":  "|".join(d.get("origin_country") or []),
        "genres":          "|".join(g["name"] for g in d.get("genres", [])),
        "keywords":        "|".join(k["name"] for k in d.get("keywords", {}).get("keywords", [])),
        "overview":        d.get("overview"),
        "vote_average":    d.get("vote_average"),
        "vote_count":      d.get("vote_count"),
        "popularity":      d.get("popularity"),
        "in_collection":   collection is not None,
        "collection_name": collection["name"] if collection else None,
        "director":        first_with_job("Director"),
        "cinematographer": first_with_job("Director of Photography"),
        "cast_top5":       "|".join(c["name"] for c in cast[:5]),
        "poster_path":     d.get("poster_path"),
    }


GONE = {"gone_from_tmdb": True}      # cached for a film TMDB returns 404 for


def fetch_all_details(tmdb_ids, *, headers, cache_path=None, store=None, progress=None, delay=None):
    """Fetch and parse detail records for every TMDB ID.

    A local cache keeps the raw responses; a shared store keeps the parsed record. A film TMDB
    no longer has (404) is skipped and reported, rather than stopping the whole run.
    """
    keys = [str(int(t)) for t in tmdb_ids]
    cache = _Cache(keys, cache_path, store)
    rows, missing = [], []

    def lookup(key):
        try:
            raw = fetch_details(int(key), headers=headers)
        except requests.HTTPError as e:
            if e.response is None or e.response.status_code != 404:
                raise
            return GONE                               # remembered, so it isn't asked for again
        return parse_details(raw) if store is not None else raw

    todo = list(dict.fromkeys(k for k in keys if k not in cache))
    new_calls = _lookup_many(todo, lookup, cache=cache, progress=progress, total=len(keys),
                             done_already=len(keys) - len(todo))

    for key in keys:
        if cache[key] == GONE:
            missing.append(key)
            continue
        rows.append(cache[key] if store is not None else parse_details(cache[key]))

    cache.flush()
    print(f"done — {new_calls} new API calls, {len(rows) - new_calls} from cache"
          + (f", {len(missing)} no longer on TMDB" if missing else ""))
    return pd.DataFrame(rows, columns=list(PARSED_COLUMNS))

# ---------- Upcoming releases ----------

def discover_upcoming(start, end, *, headers, pages=2, region=None):
    """Films released between start and end, most popular first.

    Without a region, filters on the primary (worldwide first) release date.
    With a region, filters on that region's theatrical releases, limited or wide.
    """
    params = {"sort_by": "popularity.desc", "include_adult": False}
    if region:
        params.update({"region": region,
                       "release_date.gte": start,
                       "release_date.lte": end,
                       "with_release_type": "2|3"})
    else:
        params.update({"primary_release_date.gte": start,
                       "primary_release_date.lte": end})

    results = []
    for page in range(1, pages + 1):
        results.extend(_get("https://api.themoviedb.org/3/discover/movie",
                            params={**params, "page": page}, headers=headers)["results"])
    return [{"id": r["id"], "release_date": r.get("release_date")} for r in results]

# ---------- Posters to blur in the app ----------

SENSITIVE_TAG = re.compile(
    r"unsimulated sex|explicite? sex"
    r"|erotic|eroticism|erotica"
    r"|erotic (?:movie|film|thriller|drama|romance|comedy|fantasy|horror)"
    r"|softcore.*"
    r"|(?:(?:fe)?male )?nudity"
)


def sensitive_poster(keywords):
    """True where any TMDB keyword fully matches SENSITIVE_TAG; keywords are '|'-joined strings."""
    return (keywords.fillna("").str.split("|")
            .apply(lambda tags: any(SENSITIVE_TAG.fullmatch(t.strip()) for t in tags)))