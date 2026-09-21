"""TMDB matching and details — moved from 02_tmdb_enrichment.ipynb.

Nothing here reads .env or hard-codes a cache location: the caller builds headers
with make_headers(token) and passes cache paths in, so the same code serves any
user's export and any cache (rated films, watchlist).
"""

import json
import re
import time
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd
import requests


# ---------- API access ----------

def make_headers(token):
    """Request headers for the TMDB v4 Read Access Token (Bearer), not the v3 api_key."""
    return {"Authorization": f"Bearer {token}", "accept": "application/json"}


def search_film(title, year=None, *, headers):
    params = {"query": title, "include_adult": True}
    if year:
        params["year"] = year
    r = requests.get("https://api.themoviedb.org/3/search/movie",
                     params=params, headers=headers, timeout=15)
    r.raise_for_status()
    return r.json()["results"]


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


def match_all(films, *, headers, cache_path, delay=0.05):
    """Match every film to TMDB, caching raw search responses."""
    cache_path = Path(cache_path)
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    rows, new_calls = [], 0

    for i, film in enumerate(films.itertuples(index=False), start=1):
        key = film.film_key
        year = None if pd.isna(film.film_year) else int(film.film_year)

        if key not in cache:
            results = search_film(film.film_title, year, headers=headers)
            if not results:
                results = search_film(film.film_title, headers=headers)   # year mismatch fallback
            cache[key] = results
            new_calls += 1
            time.sleep(delay)

            if new_calls % 100 == 0:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(json.dumps(cache))
                print(f"  {i}/{len(films)} processed ({new_calls} API calls)")

        match = best_match(cache[key], film.film_title, year)
        if match is None:
            match = {"tmdb_id": None, "matched_title": None, "matched_year": None,
                     "confidence": "no_match", "similarity": 0.0, "vote_count": None}

        rows.append({"film_key": key, "film_title": film.film_title,
                     "film_year": film.film_year, **match})

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache))
    print(f"done — {new_calls} new API calls, {len(rows) - new_calls} from cache")
    return pd.DataFrame(rows)


# ---------- Film details ----------

def fetch_details(tmdb_id, *, headers):
    r = requests.get(f"https://api.themoviedb.org/3/movie/{tmdb_id}",
                     params={"append_to_response": "credits,keywords"},
                     headers=headers, timeout=15)
    r.raise_for_status()
    return r.json()


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


def fetch_all_details(tmdb_ids, *, headers, cache_path, delay=0.05):
    """Fetch and parse detail records for every TMDB ID, caching raw responses."""
    cache_path = Path(cache_path)
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    rows, new_calls = [], 0

    for i, tmdb_id in enumerate(tmdb_ids, start=1):
        key = str(int(tmdb_id))

        if key not in cache:
            cache[key] = fetch_details(int(tmdb_id), headers=headers)
            new_calls += 1
            time.sleep(delay)

            if new_calls % 100 == 0:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(json.dumps(cache))
                print(f"  {i}/{len(tmdb_ids)} processed ({new_calls} API calls)")

        rows.append(parse_details(cache[key]))

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache))
    print(f"done — {new_calls} new API calls, {len(rows) - new_calls} from cache")
    return pd.DataFrame(rows)

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
        r = requests.get("https://api.themoviedb.org/3/discover/movie",
                         params={**params, "page": page},
                         headers=headers, timeout=15)
        r.raise_for_status()
        results.extend(r.json()["results"])
    return results