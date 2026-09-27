"""The app's side of uploaded runs: which runs this browser knows, and what it can do with them.

A browser learns a run's id three ways — it uploaded it this session, a cookie remembers it from
an earlier visit, or it arrived by the run's private link (?u=run:<id>). The cookie holds run ids
only, never data, and lasts as long as the data does.
"""

import io
import json
import logging
import re
import zipfile
from urllib.parse import urlsplit

import streamlit as st

from src import store
from src.app_data import APP_FILES, RUN_PREFIX, is_run, run_files, run_id
from src.runner import Runner, is_stale, tmdb_token

COOKIE      = "btcs_runs"
MAX_RUNS    = 5                          # a browser remembers at most this many uploads
ID_PATTERN  = re.compile(r"^[A-Za-z0-9_-]{20,40}$")
BUNDLE_TAG  = "beyond-the-crowd-score.json"


log = logging.getLogger(__name__)


# ---------- The runner ----------

@st.cache_resource(show_spinner=False)
def get_runner():
    """One runner, and so one worker thread, per server process."""
    token = tmdb_token()
    if not token:
        return None
    return Runner(token)


@st.cache_resource(ttl=6 * 3600, show_spinner=False)
def sweep_expired():
    """Delete runs past their 90 days — at most once every six hours per server process.

    This is the app's stand-in for Firestore's TTL deletion, which needs billing enabled.
    A failure here must never break the page, so it's logged and tried again next time.
    """
    try:
        n = store.delete_expired()
        if n:
            log.info("deleted %d expired run(s)", n)
        return n
    except Exception:
        log.exception("sweeping expired runs failed")
        sweep_expired.clear()
        return 0


# ---------- Which runs this browser knows ----------

def _valid(rid):
    return isinstance(rid, str) and bool(ID_PATTERN.match(rid))


@st.cache_data(ttl=10, show_spinner=False)
def run_doc(rid):
    """A run's record, briefly cached: every page reads it, and it only changes while running."""
    return store.get_run(rid)


def known_runs():
    """This browser's run ids, newest first: this session's, the cookie's, and any in the link."""
    ids = st.session_state.setdefault("my_runs", [])
    if not st.session_state.get("_runs_loaded"):
        cookie = st.context.cookies.get(COOKIE, "")
        ids.extend(r for r in cookie.split(".") if _valid(r) and r not in ids)
        st.session_state["_runs_loaded"] = True
    linked = st.query_params.get("u", "")
    if is_run(linked) and _valid(run_id(linked)) and run_id(linked) not in ids:
        ids.insert(0, run_id(linked))
    ids[:] = [r for r in ids if run_doc(r) is not None][:MAX_RUNS]    # drop deleted or expired
    return list(ids)


def remember(rid):
    ids = st.session_state.setdefault("my_runs", [])
    if rid in ids:
        ids.remove(rid)
    ids.insert(0, rid)
    del ids[MAX_RUNS:]


def forget(rid):
    ids = st.session_state.setdefault("my_runs", [])
    if rid in ids:
        ids.remove(rid)


def sync_cookie():
    """Write the run ids to the browser's cookie when they've changed. Called once per run of app.py.

    Streamlit can read cookies but not set them, so a one-line script does it from the page. The
    value is only ever validated run ids joined by dots — nothing a visitor typed.
    """
    value = ".".join(st.session_state.get("my_runs", []))
    if value == st.session_state.get("_cookie_written", st.context.cookies.get(COOKIE, "")):
        return
    age = 0 if not value else 90 * 24 * 3600
    st.html(f"<script>document.cookie = '{COOKIE}={value}; max-age={age}; path=/; "
            f"SameSite=Lax';</script>", unsafe_allow_javascript=True)
    st.session_state["_cookie_written"] = value


def ready_viewers():
    """This browser's finished runs, as viewer keys for the Viewing pills."""
    out = []
    for rid in known_runs():
        doc = run_doc(rid)
        if doc and doc.get("status") == "done":
            out.append(RUN_PREFIX + rid)
    return out


def switch_to(viewer):
    """Show a viewer on the next run of the app (applied in app.py before the pills are drawn)."""
    st.session_state["_switch_user"] = viewer


# ---------- Links, downloads, deletion ----------

def private_link(rid):
    """A link that opens the app on this run, in any browser."""
    parts = urlsplit(st.context.url or "")
    base = f"{parts.scheme}://{parts.netloc}/" if parts.netloc else "/"
    return f"{base}?u={RUN_PREFIX}{rid}"


def bundle(rid):
    """Every file of a run in one zip, tagged so it can be uploaded again to restore the run."""
    files = run_files(rid)
    doc = run_doc(rid) or {}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(BUNDLE_TAG, json.dumps({"format": 1, "display_name": doc.get("display_name")}))
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


def is_bundle(data):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            return BUNDLE_TAG in z.namelist()
    except zipfile.BadZipFile:
        return False


def restore(data):
    """A results file downloaded earlier, stored again as a new run — no processing needed."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        meta = json.loads(z.read(BUNDLE_TAG))
        files = {n: z.read(n) for n in z.namelist() if n in APP_FILES}
    missing = [f for f in APP_FILES if f not in files and f != "reviews.csv"]
    if missing:
        raise ValueError("That results file is incomplete, so it can't be restored.")
    rid = store.new_run_id()
    store.create_run(rid, meta.get("display_name") or "Your films")
    store.save_files(rid, files)
    store.update_run(rid, status="done", stage="Done", progress=1.0, restored=True)
    return rid


def delete(rid):
    """Remove a run everywhere: Firestore, this browser's list, and the app's caches."""
    store.delete_run(rid)
    forget(rid)
    run_doc.clear()
    run_files.clear()
    if st.session_state.get("user") == RUN_PREFIX + rid:
        st.session_state.pop("user", None)


def touch_once(rid):
    """Viewing a run keeps it for another 90 days — once per session is plenty."""
    seen = st.session_state.setdefault("_touched", set())
    if rid not in seen:
        store.touch(rid)
        seen.add(rid)


__all__ = ["get_runner", "sweep_expired", "known_runs", "remember", "forget", "sync_cookie", "ready_viewers",
           "switch_to", "private_link", "bundle", "is_bundle", "restore", "delete", "touch_once",
           "run_doc", "is_stale"]
