"""Uploaded exports, run in the background.

One worker per server process takes uploads from a queue, one at a time, so two uploads never
fight over the machine. Each run's progress goes to its Firestore record as it happens, so the
progress page (or a visitor who closed the tab and came back) reads it from there — nothing
depends on the uploader's browser staying open.

The export itself only ever exists in memory: it's read from the upload, handed to the
pipeline, and dropped. Only the app's result files are stored.
"""

import logging
import os
import queue
import threading
import time
import traceback
from datetime import datetime, timedelta, timezone

import pandas as pd

from src import store
from src.letterboxd import load_export_zip
from src.pipeline import PipelineError, identify, run
from src.tmdb import make_headers, sensitive_poster

log = logging.getLogger(__name__)

STALE_AFTER     = timedelta(minutes=20)   # a run silent this long was cut off by a restart
WRITE_EVERY     = 2.0                     # seconds between progress writes to Firestore
CHECK_EVERY     = 3.0                     # seconds between checks for a cancellation
N_POSTERS       = 30

INTERRUPTED = ("The app restarted while this was running, so it didn't finish. "
               "Please upload your export again.")
SOMETHING_WENT_WRONG = ("Something went wrong on our side while processing your export. "
                        "Please try again in a few minutes.")


class RunCancelled(Exception):
    """The uploader cancelled: stop, and delete whatever the run had made."""


def is_cancelled(run_id):
    doc = store.get_run(run_id)
    return doc is None or doc.get("status") == "cancelled"


def is_stale(run_doc):
    """A queued or running run that hasn't reported in for a while: its server restarted."""
    if run_doc.get("status") not in ("queued", "running"):
        return False
    return datetime.now(timezone.utc) - run_doc["updated_at"] > STALE_AFTER


def poster_sample(films, n=N_POSTERS):
    """The person's best-known films with posters, for the waiting screen. Explicit ones left out."""
    f = films[films["poster_path"].notna() & ~sensitive_poster(films["keywords"])]
    return f.nlargest(n, "vote_count")["poster_path"].tolist()


class Runner:
    """The queue and its single worker thread. Create one per process (see get_runner in the app)."""

    def __init__(self, token):
        self.headers = make_headers(token)
        self.jobs = queue.Queue()
        store.client()                       # connect here, not first inside the worker thread
        self._mark_stale()
        threading.Thread(target=self._work, daemon=True, name="pipeline-runner").start()

    # ---------- the request side ----------

    def submit(self, data):
        """Check an uploaded zip and queue it. Returns the new run's id.

        Raises ValueError, worded for the uploader, if the file isn't a usable export — checked
        here so a bad upload fails in seconds rather than after a wait in the queue.
        """
        export = load_export_zip(data)
        if "watchlist" not in export:
            raise ValueError("Your export has no watchlist.csv, and the app is built around "
                             "predicting your watchlist. Add some films to it and export again.")
        user, name, region = identify(export)
        run_id = store.new_run_id()
        store.create_run(run_id, name)
        store.update_run(run_id, username=user, region=region)
        self.jobs.put((run_id, export, user, name, region))
        return run_id

    # ---------- the worker side ----------

    def _mark_stale(self):
        """Runs left queued or running by a previous server process will never finish."""
        for run_id, doc in store.active_runs():
            if is_stale(doc):
                store.update_run(run_id, status="failed", stage="Interrupted", message=INTERRUPTED)

    def _work(self):
        while True:
            job = self.jobs.get()
            try:
                self._run_one(*job)
            except Exception:                     # never let one bad run stop the worker
                log.exception("runner: unexpected failure outside a run")
            finally:
                self.jobs.task_done()

    def _run_one(self, run_id, export, user, name, region):
        if is_cancelled(run_id):                  # cancelled while it waited in the queue
            store.delete_run(run_id)
            return

        last_write, last_check = [0.0], [0.0]

        def check_cancelled():
            now = time.monotonic()
            if now - last_check[0] >= CHECK_EVERY:
                last_check[0] = now
                if is_cancelled(run_id):
                    raise RunCancelled()

        def progress(fraction, stage, detail=""):
            check_cancelled()
            now = time.monotonic()
            if now - last_write[0] >= WRITE_EVERY or fraction >= 0.99:
                # no status here: a status write could overwrite a cancellation made meanwhile
                store.update_run(run_id, progress=round(fraction, 3), stage=stage, message=detail)
                last_write[0] = now

        def on_matched(films):
            store.update_run(run_id, posters=poster_sample(films))

        store.update_run(run_id, status="running", stage="Starting", progress=0.0)
        started = time.monotonic()
        try:
            app_files, _ = run(export, headers=self.headers,
                               date=pd.Timestamp.today().normalize(), user=user, name=name,
                               region=region, stores=store.shared_caches(), log=lambda *a: None,
                               progress=progress, on_matched=on_matched)
            if is_cancelled(run_id):
                raise RunCancelled()
            store.update_run(run_id, stage="Saving your results", progress=0.995)
            store.save_files(run_id, app_files)
            if is_cancelled(run_id):              # cancelled while saving: don't keep anything
                raise RunCancelled()
            store.update_run(run_id, status="done", stage="Done", progress=1.0, message="",
                             seconds=round(time.monotonic() - started))
        except RunCancelled:
            store.delete_run(run_id)
        except PipelineError as e:
            store.update_run(run_id, status="failed", stage="Couldn't finish", message=str(e))
        except Exception:
            log.error("runner: run %s failed\n%s", run_id, traceback.format_exc())
            store.update_run(run_id, status="failed", stage="Couldn't finish",
                             message=SOMETHING_WENT_WRONG)


def tmdb_token():
    """The TMDB token: an environment variable locally (.env), or Streamlit's secrets when deployed."""
    token = os.getenv("TMDB_TOKEN")
    if not token:
        try:
            import streamlit as st
            token = st.secrets.get("TMDB_TOKEN")
        except Exception:
            token = None
    return token
