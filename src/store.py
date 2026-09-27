"""Persistent storage for uploaded runs, in Firestore.

Layout:
  runs/{run_id}                        one document per upload: status, stage, progress, name,
                                       created/updated/expiry times
  runs/{run_id}/files/{name}__{n}      the run's result files (the same files a pipeline run
                                       writes to data/processed/<user>/), gzipped and split
                                       into chunks under Firestore's 1 MB document limit
  tmdb_{kind}/{key}                    a cache of TMDB lookups shared by every run: film data
                                       is the same whoever watched the film, so each upload
                                       only fetches the films nobody has uploaded before

Every run document and chunk carries `expires_at`; viewing a run pushes the date back, so only
abandoned runs expire. Firestore's own TTL deletion needs billing enabled, so the project stays
on the free plan and the app does it instead: an expired run reads as gone straight away, and
delete_expired() removes it (the app calls it every few hours while running).
The shared TMDB cache never expires: it holds public film data, not anyone's ratings.
"""

import gzip
import hashlib
import secrets
import tomllib
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from google.cloud import firestore
from google.oauth2 import service_account

ROOT          = Path(__file__).resolve().parent.parent
KEEP_FOR      = timedelta(days=90)
CHUNK_BYTES   = 900_000          # under the 1 MiB document limit, with room for the other fields
CHUNKS_PER_WRITE = 8             # keeps each batched request well under Firestore's size limit
CACHE_BATCH   = 300


# ---------- Connection ----------

def _credentials_info():
    """The service account key: Streamlit's secrets when running in the app, else the local file."""
    try:
        import streamlit as st
        if "firestore" in st.secrets:
            return dict(st.secrets["firestore"])
    except Exception:
        pass
    with open(ROOT / ".streamlit" / "secrets.toml", "rb") as f:
        return tomllib.load(f)["firestore"]


def configured():
    """Whether Firestore credentials are available. Without them the app still runs — the example
    viewers need no database — and only uploads are switched off."""
    try:
        return bool(_credentials_info().get("project_id"))
    except Exception:
        return False


@lru_cache(maxsize=1)
def client():
    info = _credentials_info()
    creds = service_account.Credentials.from_service_account_info(info)
    return firestore.Client(credentials=creds, project=info["project_id"])


def _now():
    return datetime.now(timezone.utc)


# ---------- Runs ----------

def new_run_id():
    """A long random id: the run's private link. Unguessable, so the link is the access control."""
    return secrets.token_urlsafe(18)


def _run(run_id):
    return client().collection("runs").document(run_id)


def create_run(run_id, display_name):
    now = _now()
    _run(run_id).set({
        "display_name": display_name,
        "status": "queued",              # queued → running → done | failed
        "stage": "Waiting to start",
        "progress": 0.0,                 # 0 to 1, for the progress bar
        "message": "",
        "created_at": now,
        "updated_at": now,
        "expires_at": now + KEEP_FOR,
    })


def update_run(run_id, **fields):
    """Merge fields into the run (status, stage, progress, message…) and push back its expiry."""
    now = _now()
    _run(run_id).set({**fields, "updated_at": now, "expires_at": now + KEEP_FOR}, merge=True)


def get_run(run_id):
    """The run's document as a dict, or None if it doesn't exist (never did, deleted or expired).

    A run past its expiry date reads as gone at once, even before delete_expired() removes it.
    """
    if not run_id:
        return None
    snap = _run(run_id).get()
    if not snap.exists:
        return None
    doc = snap.to_dict()
    if doc.get("expires_at") and doc["expires_at"] <= _now():
        return None
    return doc


def delete_expired():
    """Delete every run, with its files, whose expiry date has passed. Returns how many."""
    expired = (client().collection("runs")
               .where(filter=firestore.FieldFilter("expires_at", "<=", _now()))
               .stream())
    n = 0
    for snap in expired:
        delete_run(snap.id)
        n += 1
    return n


def touch(run_id):
    """Someone viewed the run: keep it, and its files, for another 90 days from now."""
    expires = _now() + KEEP_FOR
    _run(run_id).set({"expires_at": expires}, merge=True)
    batch, n = client().batch(), 0
    for ref in _run(run_id).collection("files").list_documents():
        batch.update(ref, {"expires_at": expires})
        n += 1
        if n % 400 == 0:
            batch.commit()
            batch = client().batch()
    batch.commit()


def active_runs():
    """Runs waiting or in progress, oldest first. Only ever a handful, so they're fetched and
    sorted here rather than with a two-field query, which would need a Firestore index."""
    snaps = (client().collection("runs")
             .where(filter=firestore.FieldFilter("status", "in", ["queued", "running"]))
             .stream())
    runs = [(s.id, s.to_dict()) for s in snaps]
    return sorted(runs, key=lambda r: r[1]["created_at"])


def queued_before(run_id):
    """How many runs are waiting or running ahead of this one — its place in the queue."""
    ids = [rid for rid, _ in active_runs()]
    return ids.index(run_id) if run_id in ids else 0


def delete_run(run_id):
    """Remove a run and every file it holds, immediately."""
    files = list(_run(run_id).collection("files").list_documents())
    for i in range(0, len(files), 400):
        batch = client().batch()
        for ref in files[i:i + 400]:
            batch.delete(ref)
        batch.commit()
    _run(run_id).delete()


# ---------- Result files ----------

def pack(data):
    """Gzip bytes and split them into chunks small enough for one document each."""
    packed = gzip.compress(data, compresslevel=9)
    return [packed[i:i + CHUNK_BYTES] for i in range(0, len(packed), CHUNK_BYTES)] or [b""]


def unpack(chunks):
    return gzip.decompress(b"".join(chunks))


def save_files(run_id, files):
    """Store {filename: bytes} for a run, replacing any earlier copy of those files."""
    folder = _run(run_id).collection("files")
    expires = _now() + KEEP_FOR
    for name, data in files.items():
        for ref in folder.where(filter=firestore.FieldFilter("name", "==", name)).stream():
            ref.reference.delete()
        chunks = pack(data)
        for start in range(0, len(chunks), CHUNKS_PER_WRITE):
            batch = client().batch()
            for i, chunk in enumerate(chunks[start:start + CHUNKS_PER_WRITE], start=start):
                batch.set(folder.document(f"{name}__{i:03d}"),
                          {"name": name, "index": i, "total": len(chunks),
                           "data": chunk, "expires_at": expires})
            batch.commit()


def load_files(run_id):
    """A run's files as {filename: bytes}. A file with a chunk missing is left out, not half-read."""
    parts = {}
    for snap in _run(run_id).collection("files").stream():
        d = snap.to_dict()
        parts.setdefault(d["name"], {})[d["index"]] = (d["total"], d["data"])
    files = {}
    for name, chunks in parts.items():
        total = next(iter(chunks.values()))[0]
        if len(chunks) == total:
            files[name] = unpack([chunks[i][1] for i in range(total)])
    return files


# ---------- Shared TMDB cache ----------

def _cache_id(key):
    """Firestore document ids can't contain '/', which film titles can ('Fahrenheit 9/11')."""
    return hashlib.sha1(str(key).encode()).hexdigest()


def cache_get(kind, keys):
    """Cached values for the keys that have one, as {key: value}. `kind` is e.g. 'details'."""
    keys = list(dict.fromkeys(str(k) for k in keys))
    folder = client().collection(f"tmdb_{kind}")
    found = {}
    for i in range(0, len(keys), CACHE_BATCH):
        refs = [folder.document(_cache_id(k)) for k in keys[i:i + CACHE_BATCH]]
        for snap in client().get_all(refs):
            if snap.exists:
                d = snap.to_dict()
                found[d["key"]] = d["value"]
    return found


class SharedCache:
    """The shared TMDB cache for one kind of lookup, in the shape the pipeline expects."""

    def __init__(self, kind):
        self.kind = kind

    def get_many(self, keys):
        return cache_get(self.kind, keys)

    def put_many(self, items):
        cache_put(self.kind, items)


def shared_caches():
    """The stores a pipeline run in the app uses: searches, film details, upcoming releases."""
    return {kind: SharedCache(kind) for kind in ("search", "details", "discover")}


def cache_put(kind, items):
    """Store {key: value} in the shared cache. Values must be plain JSON-like data."""
    folder = client().collection(f"tmdb_{kind}")
    items = list(items.items())
    for i in range(0, len(items), 400):
        batch = client().batch()
        for key, value in items[i:i + 400]:
            batch.set(folder.document(_cache_id(key)), {"key": str(key), "value": value})
        batch.commit()
