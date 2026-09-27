import html
import random
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from src import store
from src.app_data import RUN_PREFIX, list_users, load_tables, possessive
from src.app_runs import (bundle, delete, get_runner, is_bundle, is_stale, known_runs,
                          private_link, remember, restore, run_doc, switch_to)
from src.app_ui import page_title, poster_url
from src.runner import INTERRUPTED

page_title("Your films")

EXPORT_HELP = "https://letterboxd.com/settings/data/"


# ---------- Poster carousel ----------

@st.cache_data(show_spinner=False)
def example_posters(n=40):
    """Posters from the example viewers' films, for before an upload's own films are matched."""
    paths = []
    for user in list_users():
        t = load_tables(user)
        for table in ("test", "watchlist"):
            df = t[table]
            if "sensitive_poster" in df:
                df = df[~df["sensitive_poster"].astype(bool)]
            paths += df.nlargest(60, "vote_count")["poster_path"].dropna().tolist()
    paths = list(dict.fromkeys(paths))
    random.Random(7).shuffle(paths)
    return paths[:n]


def carousel(paths):
    """Two rows of posters drifting in opposite directions. Pure CSS: it keeps moving smoothly
    while the progress underneath refreshes, and 'Reduce motion' stops it."""
    urls = [poster_url(p) for p in paths if isinstance(p, str)]
    if len(urls) < 6:
        return
    half = len(urls) // 2
    rows = []
    for i, row in enumerate([urls[:half], urls[half:]]):
        imgs = "".join(f"<img src='{u}' alt='' loading='lazy'>" for u in row * 2)   # doubled: seamless loop
        rows.append(f"<div class='reel-track{' reverse' if i else ''}'>{imgs}</div>")
    st.markdown(f"<div class='poster-reel' aria-hidden='true'>{''.join(rows)}</div>",
                unsafe_allow_html=True)


# ---------- The states of a run ----------

def elapsed(doc):
    secs = int((datetime.now(timezone.utc) - doc["created_at"]).total_seconds())
    return f"{secs // 60}m {secs % 60:02d}s" if secs >= 60 else f"{secs}s"


@st.fragment(run_every=2)
def live_progress(rid, showing_own_posters):
    """Re-reads the run every two seconds. Anything that changes the page's layout — finishing,
    failing, or the person's own posters arriving — reruns the whole page instead."""
    doc = store.get_run(rid)
    if doc is None:
        st.rerun(scope="app")
    if doc["status"] in ("done", "failed") or is_stale(doc):
        run_doc.clear()
        st.rerun(scope="app")
    if doc.get("posters") and not showing_own_posters:
        st.rerun(scope="app")

    if doc["status"] == "queued":
        ahead = store.queued_before(rid)
        st.progress(0.0, text="Waiting to start")
        st.markdown(f"<p class='card-meta'>{'You’re next in line' if ahead <= 1 else f'{ahead} uploads ahead of you'}"
                    f" — each takes a few minutes. You can close this page and come back: it keeps "
                    f"your place.</p>", unsafe_allow_html=True)
    else:
        st.progress(min(float(doc.get("progress", 0)), 1.0), text=doc.get("stage", "Working"))
        detail = f" · {html.escape(doc['message'])}" if doc.get("message") else ""
        st.markdown(f"<p class='card-meta'>{elapsed(doc)} so far{detail}. Usually 3–6 minutes, less if "
                    f"other people have uploaded the same films. You can close this page and come "
                    f"back — it carries on without you.</p>", unsafe_allow_html=True)


def show_running(rid, doc):
    own = doc.get("posters") or []
    st.header(f"Building {possessive(doc['display_name'])} predictions", anchor=False)
    carousel(own if len(own) >= 12 else example_posters())
    if own:
        st.markdown("<p class='card-meta' style='text-align:center'>Some of the films you've "
                    "rated</p>", unsafe_allow_html=True)
    live_progress(rid, bool(own))

    st.markdown("<p class='card-meta' style='margin-top:1rem'><b style='color:var(--white)'>Your "
                "private link</b> — keep it to come back to this upload from anywhere, before or "
                "after it finishes. Anyone with it can see your films once they're ready.</p>",
                unsafe_allow_html=True)
    st.code(private_link(rid), language=None, wrap_lines=True)


def show_done(rid, doc):
    name = doc["display_name"]
    viewer = RUN_PREFIX + rid
    t = load_tables(viewer)
    s = t["model_summary"]
    took = f" in {doc['seconds'] // 60}m {doc['seconds'] % 60:02d}s" if doc.get("seconds") else ""
    st.header(f"{possessive(name)} films are ready", anchor=False)
    st.markdown(
        f"<p class='lead'>{int(s['n_rated']):,} rated films modelled{took}, and "
        f"{len(t['watchlist']):,} watchlist films predicted. On the films held back for testing, "
        f"the model was off by <b>{s['mae_deploy']:.2f}&nbsp;★</b> on average, against "
        f"<b>{s['mae_m1']:.2f}&nbsp;★</b> for the crowd score.</p>",
        unsafe_allow_html=True)

    total, used = t["profile"].get("n_rated_entries"), int(s["n_rated"])
    if pd.notna(total) and int(total) > used:           # older uploads didn't record the total
        left = int(total) - used
        st.markdown(
            f"<p class='card-meta'>{used:,} of your {int(total):,} rated diary entries were matched "
            f"to TMDB with confidence. The other {left:,} {'was' if left == 1 else 'were'} left out "
            f"rather than guessed at — usually a title shared by several films, or a year that "
            f"doesn't line up — so every prediction here rests on films the app is sure of.</p>",
            unsafe_allow_html=True)

    def open_films():
        switch_to(viewer)
    if st.button("See my films →", type="primary", on_click=open_films):
        st.switch_page("app_pages/0_intro.py")

    st.subheader("Keep them", anchor=False)
    st.markdown("<p class='card-meta'>This browser remembers your films for 90 days after you last "
                "looked at them. To open them anywhere else, use your private link — anyone with it "
                "can see your films, so share it only if you mean to.</p>", unsafe_allow_html=True)
    st.code(private_link(rid), language=None, wrap_lines=True)

    with st.container(horizontal=True, gap="small"):
        st.download_button("Download everything", bundle(rid), icon=":material/download:",
                           file_name=f"beyond-the-crowd-score-{t['profile'].get('username', 'films')}.zip",
                           mime="application/zip",
                           help="All your results in one file. Upload it here again to bring your films "
                                "back instantly, without processing your export again.")
        st.download_button("Watchlist predictions (CSV)", t["watchlist"].to_csv(index=False),
                           file_name="watchlist_predictions.csv", mime="text/csv")
        st.download_button("Coming soon (CSV)", t["coming"].to_csv(index=False),
                           file_name="coming_soon.csv", mime="text/csv")

    st.subheader("Delete them", anchor=False)
    with st.popover("Delete my data", icon=":material/delete:"):
        st.markdown("This removes your results from the app permanently, straight away. Anything "
                    "you've downloaded stays yours.")
        if st.button("Yes, delete everything", type="primary", key=f"del_{rid}"):
            delete(rid)
            st.rerun()


def show_failed(rid, doc):
    interrupted = is_stale(doc)
    st.header("That didn't work", anchor=False)
    st.error(INTERRUPTED if interrupted else doc.get("message") or "Something went wrong.")
    if st.button("Try again with another upload", type="primary"):
        delete(rid)
        st.rerun()


# ---------- Upload ----------

def upload_form(first):
    runner = get_runner()
    if first:
        st.header("Your films", anchor=False)
        st.markdown(
            "<p class='lead'>Upload your own Letterboxd export and the same model is built for you: "
            "tested against the crowd score on your own films, then used to predict your "
            "watchlist.</p>",
            unsafe_allow_html=True)
    st.markdown(
        f"<p class='card-meta'><b style='color:var(--white)'>Getting your export:</b> on Letterboxd, "
        f"go to <a href='{EXPORT_HELP}' target='_blank'>Settings → Data → Export your data</a>. "
        f"Upload the .zip it gives you, unopened. You'll need at least 300 rated diary entries and "
        f"a watchlist.</p>"
        "<p class='card-meta'><b style='color:var(--white)'>What's kept:</b> your export is read in "
        "memory and never stored. Only the results are kept — predictions, summary figures and short "
        "excerpts from reviews that explain a prediction — and they're deleted automatically after 90 "
        "days unused, or straight away whenever you choose.</p>",
        unsafe_allow_html=True)

    if runner is None:
        st.warning("Uploads aren't available on this copy of the app: they need a TMDB token and "
                   "Firestore credentials, and one or both aren't set. The example viewers work as "
                   "normal.")
        return

    data = st.file_uploader("Your Letterboxd export, or a results file you downloaded before",
                            type="zip", key="upload")
    if data is not None and st.button("Build my predictions", type="primary"):
        raw = data.getvalue()
        try:
            rid = restore(raw) if is_bundle(raw) else runner.submit(raw)
        except ValueError as e:
            st.error(str(e))
            return
        remember(rid)
        run_doc.clear()
        st.rerun()


# ---------- Page ----------

runs = known_runs()
if not runs:
    upload_form(first=True)
else:
    rid = runs[0]                               # the most recent upload takes the page
    doc = run_doc(rid)
    if doc["status"] in ("queued", "running") and not is_stale(doc):
        show_running(rid, doc)
    elif doc["status"] == "done":
        show_done(rid, doc)
    else:
        show_failed(rid, doc)

    others = [(r, run_doc(r)) for r in runs[1:]]
    if others:
        st.subheader("Earlier uploads", anchor=False)
        for r, d in others:
            with st.container(horizontal=True, vertical_alignment="center", gap="small"):
                st.markdown(f"**{html.escape(d['display_name'])}** · {d['status']} · "
                            f"{d['created_at']:%-d %b %Y}", width="stretch")
                if d["status"] == "done" and st.button("Open", key=f"open_{r}"):
                    switch_to(RUN_PREFIX + r)
                    st.switch_page("app_pages/0_intro.py")
                if st.button("Delete", key=f"delete_{r}", icon=":material/delete:"):
                    delete(r)
                    st.rerun()

    if doc["status"] in ("done", "failed"):
        with st.expander("Upload another export"):
            upload_form(first=False)
