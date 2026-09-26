"""Shared look and formatting for the Streamlit app.

Every rating shown in the app goes through these helpers, so units are never dropped:
predictions as half-stars (3.5 ★), crowd as 6.1 / 10, gaps as +0.8 ★.
"""

import html
import unicodedata

import numpy as np
import pandas as pd
import streamlit as st
from better_profanity import profanity

POSTER_BASE = "https://image.tmdb.org/t/p/w342"

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Hanken+Grotesk:wght@400;500;600;700;800&display=swap');

:root {
    --orange:  #ff8000;
    --green:   #00e054;
    --blue:    #40bcf4;
    --dark:    #15181d;
    --surface: #2c3440;
    --slate:   #445466;
    --muted:   #98aabb;
    --white:   #ffffff;
}

html, body, .stApp, .stApp p, .stApp li, .stApp label, .stApp button, .stApp input {
    font-family: 'Hanken Grotesk', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}

.stApp h1, .stApp h2, .stApp h3 {
    font-family: 'Hanken Grotesk', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    font-weight: 700;
    letter-spacing: -0.02em;
}

.block-container, [data-testid="stMainBlockContainer"] {
    padding-top: 4rem;          /* clear of the fixed header, so the top bar isn't cut off */
    padding-bottom: 2rem;
    max-width: 1400px;
}

.stApp hr {
    border-color: var(--slate);
}

/* Lead paragraph under a page title */
.lead {
    font-size: 1.3rem;
    line-height: 1.5;
    color: var(--muted);
    max-width: 60rem;
    margin-bottom: 1.5rem;
}

.lead b {
    color: var(--white);
    font-weight: 600;
}

/* Poster cards: the whole card is one invisible button */
[class*="st-key-card_"] {
    position: relative;
    margin-bottom: 1.75rem;
}

.poster-frame {
    position: relative;
    overflow: hidden;
    border-radius: 6px;
    aspect-ratio: 2 / 3;
    margin-bottom: 0.6rem;
    background: var(--surface);
    transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.poster-frame img {
    display: block;
    width: 100%;
    height: 100%;
    object-fit: cover;
}

[class*="st-key-card_"]:hover .poster-frame {
    transform: translateY(-4px);
    box-shadow: 0 10px 24px rgba(0, 0, 0, 0.5), 0 0 0 2px var(--orange);
}

[class*="st-key-open_"] {
    position: absolute;
    inset: 0;
    z-index: 2;
}

/* Every wrapper between the card and its button has to fill the card too: buttons are
   only as wide as their label by default, which made just part of each poster clickable. */
[class*="st-key-open_"] [data-testid="stButton"],
[class*="st-key-open_"] [data-testid="stButton"] > div,
[class*="st-key-open_"] button {
    width: 100% !important;
    height: 100% !important;
}

[class*="st-key-open_"] button {
    opacity: 0;
    cursor: pointer;
}

.card-title {
    font-weight: 600;
    font-size: 1.05rem;
    line-height: 1.25;
    margin-top: 0.4rem;
}

.card-meta {
    color: var(--muted);
    font-size: 1rem;
    line-height: 1.45;
    margin-top: 0.15rem;
}

/* Top bar: "Viewing" + the name pills + the settings menu, top right */
.viewer-label {
    color: var(--muted);
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    white-space: nowrap;
}

/* Top bar: the gear matches the pills' height */
.st-key-top_bar [data-testid="stPopover"] button {
    height: 2.2rem;
    min-height: 2.2rem;
    padding: 0 0.75rem;
    margin: 0;
}

/* Settings menu: each row is the switch, then its text */
[data-testid="stPopoverBody"] {
    min-width: 23rem;
}

[class*="st-key-row_set_"] {
    margin-bottom: 0.7rem;
}

[class*="st-key-row_set_"] [data-testid="stCheckbox"] {
    margin-top: 0.1rem;         /* level the switch with the first line of its label */
}

.setting-label {
    font-weight: 600;
    font-size: 0.95rem;
    line-height: 1.3;
}

.setting-note {
    color: var(--muted);
    font-size: 0.8rem;
    line-height: 1.35;
}

/* "Open on your phone" QR in the footer — desktop only, hidden in the phone layout */
.qr-desktop {
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: 0.6rem;
}

.qr-desktop img {
    width: 64px;
    height: 64px;
    border-radius: 4px;
}

/* The rated films behind a prediction, inside the Why? modal */
.neighbours {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 1.25rem;
}

.neighbours .card-title {
    overflow-wrap: anywhere;
}

/* Model ladder (inside the film dialog) */
.ladder-top {
    display: flex;
    align-items: center;
    gap: 1.25rem;
    margin-bottom: 0.75rem;
}

.ladder-poster {
    width: 84px;
    flex: none;
    border-radius: 6px;
}

.ladder-head {
    color: var(--muted);
    font-size: 1.05rem;
    line-height: 1.6;
}

.ladder-head b {
    color: var(--white);
}

.rung {
    display: grid;
    grid-template-columns: 17rem 1fr 6.5rem;
    align-items: center;
    gap: 1rem;
    padding: 0.4rem 0;
    border-bottom: 1px solid var(--slate);
}

.rung.new {
    animation: rung-in 0.45s ease both;
}

.rung.pending {
    opacity: 0.35;
}

.rung-label {
    font-weight: 600;
}

.rung-sub {
    color: var(--muted);
    font-size: 0.82rem;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.track {
    position: relative;
    height: 28px;
}

.track::before {
    content: "";
    position: absolute;
    left: 0;
    right: 0;
    top: 50%;
    height: 2px;
    background: var(--slate);
}

.actual {
    position: absolute;
    top: 0;
    bottom: 0;
    width: 2px;
    background: var(--green);
}

.move {
    position: absolute;
    top: 50%;
    height: 2px;
    background: var(--orange);
    opacity: 0.6;
    transform: translateY(-50%);
}

.marker {
    position: absolute;
    top: 50%;
    width: 14px;
    height: 14px;
    border-radius: 50%;
    background: var(--orange);
    transform: translate(-50%, -50%);
    z-index: 2;
}

.marker.prev {
    width: 9px;
    height: 9px;
    background: var(--muted);
    opacity: 0.7;
    z-index: 1;
}

.rung-value {
    text-align: right;
    font-weight: 700;
    font-size: 1.2rem;
}

.rung-value small {
    display: block;
    color: var(--muted);
    font-weight: 400;
    font-size: 0.8rem;
}

.rung.scale {
    border-bottom: none;
}

.track-scale {
    position: relative;
    height: 1.2rem;
}

.track-scale span {
    position: absolute;
    transform: translateX(-50%);
    color: var(--muted);
    font-size: 0.8rem;
}

.ladder-summary {
    font-size: 1.1rem;
    margin-top: 0.75rem;
    animation: rung-in 0.45s ease both;
}

.ladder-summary b {
    color: var(--white);
}

.ladder-note {
    color: var(--muted);
    font-size: 0.78rem;
    margin: 0.5rem 0 0.75rem;
    line-height: 1.45;
}

@keyframes rung-in {
    from { opacity: 0; transform: translateY(6px); }
    to   { opacity: 1; transform: none; }
}

/* Hidden or missing posters: the title on a blurred (or plain) frame */
.poster-hidden img {
    filter: blur(22px) brightness(0.55);
    transform: scale(1.2);
}

.poster-label {
    position: absolute;
    inset: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 0.4rem;
    padding: 1rem;
    text-align: center;
    background: none;
}

.poster-label-title {
    color: var(--white);
    font-weight: 700;
    font-size: 1.1rem;
    line-height: 1.2;
}

.poster-label-note {
    color: var(--muted);
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
}

/* Poster card figures: labels on one grid row, values on the next, so the values
   line up even when one label wraps onto two lines */
.card-stats {
    display: grid;
    column-gap: 1.25rem;
    row-gap: 0.1rem;
    justify-content: start;
    align-items: end;
    margin-top: 0.35rem;
}

.card-stats .label {
    color: var(--muted);
    font-size: 0.75rem;
    line-height: 1.25;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}

.card-stats .value {
    font-weight: 700;
    font-size: 1.15rem;
    color: var(--white);
}

/* Intro page */
.hero-kicker {
    color: var(--orange);
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: 0.85rem;
    font-weight: 700;
    margin-top: 1rem;
}

.hero-title {
    font-size: clamp(3rem, 6vw, 5rem);
    font-weight: 800;
    line-height: 0.95;
    letter-spacing: -0.035em;
    margin: 0.5rem 0 1.25rem;
    color: var(--white);
}

.stats {
    display: flex;
    flex-wrap: wrap;
    gap: 3rem;
    padding: 1.5rem 0;
    margin: 1rem 0 2.5rem;
    border-top: 1px solid var(--slate);
    border-bottom: 1px solid var(--slate);
}

.stat-value {
    display: block;
    font-size: 2.6rem;
    font-weight: 800;
    letter-spacing: -0.02em;
    line-height: 1.1;
}

.stat-label {
    display: block;
    color: var(--muted);
    font-size: 0.95rem;
    max-width: 15rem;
}

.layers {
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: 1rem;
    margin: 1rem 0 1.75rem;
}

.layer {
    background: var(--surface);
    border-radius: 10px;
    border-top: 4px solid var(--slate);
    padding: 1.1rem 1.1rem 1.25rem;
}

.layer-num {
    color: var(--muted);
    font-size: 0.8rem;
    font-weight: 700;
    letter-spacing: 0.08em;
}

.layer-label {
    font-size: 1.2rem;
    font-weight: 700;
    margin: 0.2rem 0;
}

.layer-sub {
    color: var(--muted);
    font-size: 0.9rem;
    margin-bottom: 0.7rem;
}

.layer p {
    font-size: 0.95rem;
    line-height: 1.5;
    margin: 0;
}

.rule {
    border-left: 3px solid var(--green);
    padding: 0.4rem 0 0.4rem 1rem;
    margin-bottom: 1.5rem;
    color: var(--muted);
    max-width: 60rem;
    line-height: 1.5;
}

.rule b {
    color: var(--white);
}

/* Mode switches on the watchlist and coming-soon pages (keyed widgets get st-key-<key> classes) */
.st-key-wl_mode button,
.st-key-cs_mode button {
    padding: 0.55rem 1.3rem;
    min-height: 3rem;
}

.st-key-wl_mode button p,
.st-key-cs_mode button p {
    font-size: 1.15rem;
}

.st-key-wl_known label p,
.st-key-wl_known [data-testid="stWidgetLabel"] p {
    font-size: 1.05rem;
}

/* ---------- Phones (desktop unaffected: nothing here applies above 640px) ---------- */
@media (max-width: 640px) {

    .block-container, [data-testid="stMainBlockContainer"] {
        padding-left: 0.9rem !important;
        padding-right: 0.9rem !important;
        padding-top: 4.25rem !important;
    }

    .neighbours { grid-template-columns: 1fr; gap: 0.9rem; }

    [data-testid="stPopoverBody"] { min-width: 0; max-width: 92vw; }
    .viewer-label { display: none; }

    .qr-desktop { display: none !important; }

    /* poster grids: three across, not one giant poster per row */
    [data-testid="stHorizontalBlock"]:has([class*="st-key-card_"]) {
        flex-wrap: wrap !important;
        gap: 1rem 0.6rem !important;
    }
    [data-testid="stHorizontalBlock"]:has([class*="st-key-card_"]) > [data-testid="stColumn"] {
        flex: 0 0 calc((100% - 1.2rem) / 3) !important;
        width: calc((100% - 1.2rem) / 3) !important;
        min-width: 0 !important;
    }
    .card-title                 { font-size: 0.85rem; }
    .card-meta                  { font-size: 0.8rem; }
    .card-stats                 { column-gap: 0.5rem; }
    .card-stats .label          { font-size: 0.58rem; letter-spacing: 0.02em; }
    .card-stats .value          { font-size: 0.85rem; }
    .poster-label-title         { font-size: 0.8rem; }

    /* pager: previous · page · of N · next on one line */
    [class*="st-key-pager_"] [data-testid="stHorizontalBlock"] {
        flex-wrap: nowrap !important;
        gap: 0.4rem !important;
    }
    [class*="st-key-pager_"] [data-testid="stColumn"] {
        flex: 1 1 auto !important;
        width: auto !important;
        min-width: 0 !important;
    }
    [class*="st-key-pager_"] [data-testid="stColumn"]:nth-child(1),
    [class*="st-key-pager_"] [data-testid="stColumn"]:nth-child(3),
    [class*="st-key-pager_"] [data-testid="stColumn"]:nth-child(7),
    [class*="st-key-pager_"] [data-testid="stColumn"]:nth-child(8) {
        display: none !important;
    }

    /* intro */
    .hero-title   { font-size: 2.6rem; }
    .lead         { font-size: 1.05rem; }
    .stats        { gap: 1.25rem 2rem; padding: 1rem 0; }
    .stat-value   { font-size: 1.9rem; }
    .stat-label   { font-size: 0.85rem; }
    .layers       { grid-template-columns: 1fr; gap: 0.6rem; }

    /* the ladder: label and value on one line, the track full width beneath */
    .rung {
        grid-template-columns: 1fr auto;
        row-gap: 0.35rem;
        column-gap: 0.75rem;
    }
    .rung > .track, .rung > .track-scale { grid-column: 1 / -1; grid-row: 2; }
    .rung > .rung-value                  { grid-column: 2; grid-row: 1; }
    .rung.scale > div:empty              { display: none; }
    .rung-label  { font-size: 0.95rem; }
    .rung-sub    { font-size: 0.8rem; }
    .rung-value  { font-size: 1rem; }

    /* modals */
    .ladder-top    { gap: 0.9rem; }
    .ladder-poster { width: 64px; }

    /* mode switches wrap rather than overflow */
    .st-key-wl_mode button, .st-key-cs_mode button { min-height: 2.2rem; padding: 0.3rem 0.65rem; }
    .st-key-wl_mode button p, .st-key-cs_mode button p { font-size: 0.9rem; }
}

"""


def inject_css():
    st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)


# ---------- Formatting: every number carries its unit ----------

def half_star(x):
    """Round to the nearest half-star, halves always rounding up (4.25 -> 4.5)."""
    return np.floor(x * 2 + 0.5) / 2


def stars(x):
    """Prediction or rating for display: '3.5 ★' (non-breaking space keeps the star with its number)."""
    return "—" if pd.isna(x) else f"{half_star(x):.1f}\u00a0★"


def stars_exact(x):
    """Unrounded prediction, shown small beside the half-star: '3.74 ★'."""
    return "—" if pd.isna(x) else f"{x:.2f}\u00a0★"


def crowd(x):
    """TMDB crowd score: '6.1 / 10'."""
    return "—" if pd.isna(x) else f"{x:.1f}\u00a0/\u00a010"


def gap(x):
    """Signed difference in stars, with a true minus sign: '+0.8 ★', '−0.3 ★'."""
    return "—" if pd.isna(x) else f"{x:+.1f}\u00a0★".replace("-", "−")


def poster_url(path):
    """Full TMDB poster URL, or None when the film has no poster."""
    return None if pd.isna(path) or not path else POSTER_BASE + path

# ---------- Viewer settings (set from the ⚙ menu in app.py) ----------

def blur_on():
    """Whether posters TMDB marks explicit are blurred — on unless the viewer turns it off."""
    return st.session_state.get("set_blur", True)


def pred_text(x):
    """A prediction on a card: half-stars by default, two decimals if the viewer asked for them."""
    return stars_exact(x) if st.session_state.get("set_exact", False) else stars(x)


def thumb_html(url, sensitive):
    """The small poster at the top of a modal, blurred if the film is flagged and blurring is on."""
    if not url:
        return ""
    if sensitive and blur_on():
        return (f"<div class='poster-frame poster-hidden' style='width:84px; flex:none; margin:0'>"
                f"<img src='{url}' alt=''></div>")
    return f"<img class='ladder-poster' src='{url}'>"


# Words the library flags that are ordinary in film reviews: titles and plot (City of God,
# Memories of Murder), names (Lee Chang-dong, Sissy Spacek), identity terms, and mild
# conversational words. Built from the flagged words in the published reviews; everything
# else the library lists stays masked.
REVIEW_WHITELIST = [
    "god", "omg", "murder", "kill", "rape", "raped", "stroke", "drunk", "naked", "sex", "sexual",
    "erotic", "porn", "porno", "lust", "horny", "horniest", "sleazy", "sleaze", "vagina", "penis",
    "voyeur", "perversion", "sadist", "hooker", "nazi", "opiate", "pot",
    "dong", "guido", "sissy", "dick",
    "gay", "queer",
    "hell", "damn", "crap", "ugly", "stupid", "jerk", "suck", "sucked", "weirdo", "willies",
    "lmao", "lmfao", "wtf",
]


@st.cache_resource
def _profanity_filter():
    """The library's own word list, minus words that are ordinary in film reviews. Loaded once."""
    profanity.load_censor_words(whitelist_words=REVIEW_WHITELIST)
    return profanity


def censor_review(text):
    """Mask strong language in a review excerpt: each flagged word becomes '****'. Always on."""
    return _profanity_filter().censor(text, "*")


# ---------- Page titles, links and shared links ----------

SITE = "Beyond the Crowd Score"


def page_title(name=None):
    """This page's browser-tab title: 'Watchlist · Beyond the Crowd Score'."""
    st.set_page_config(page_title=f"{name} · {SITE}" if name else SITE)


def fold(text):
    """Lower-case and strip accents, so a search for 'amelie' finds 'Amélie'."""
    text = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in text if not unicodedata.combining(c)).casefold()


def letterboxd_url(film):
    """The film's Letterboxd page: its own link when we have one, else Letterboxd's TMDB redirect."""
    uri = film.get("film_uri")
    if isinstance(uri, str) and uri.startswith("http"):
        return uri
    tmdb_id = film.get("tmdb_id")
    return None if pd.isna(tmdb_id) else f"https://letterboxd.com/tmdb/{int(tmdb_id)}/"


def share_url(tmdb_id):
    """A link that opens this page, for this viewer, with this film's details already open."""
    base = (st.context.url or "").split("?")[0]
    return f"{base}?u={st.session_state.get('user', '')}&film={int(tmdb_id)}"


def film_links(film):
    """The foot of a film's modal: open it on Letterboxd, and a copyable link to this prediction."""
    url = letterboxd_url(film)
    if url:
        st.link_button("Open on Letterboxd", url, icon=":material/open_in_new:",
                       icon_position="right", type="tertiary")
    if pd.notna(film.get("tmdb_id")):
        st.markdown("<p class='card-meta' style='margin:0.4rem 0 0.2rem'>Link to this prediction</p>",
                    unsafe_allow_html=True)
        st.code(share_url(film["tmdb_id"]), language=None, wrap_lines=True)


def new_dialog():
    """Call whenever a film is opened. Streamlit identifies a dialog by where it sits on the page,
    so without a fresh slot, a film opened just after closing another reuses the closed dialog and
    stays shut."""
    st.session_state["dialog_n"] = st.session_state.get("dialog_n", 0) + 1


def dialog_slot():
    """A container unique to the current opening, for the film's dialog to sit in."""
    return st.container(key=f"dialog_{st.session_state.get('dialog_n', 0)}")


def take_shared_film():
    """The TMDB id from a shared link (?film=…), read once and then removed from the address,
    so closing the modal doesn't reopen it."""
    raw = st.query_params.get("film")
    if raw is None:
        return None
    del st.query_params["film"]
    try:
        return int(raw)
    except ValueError:
        return None


# ---------- Poster cards ----------

def card_stats(pairs):
    """Small uppercase labels above large values: [('Predicted', '4.5 ★'), ('Crowd', '7.6 / 10')]."""
    labels = "".join(f"<span class='label'>{label}</span>" for label, _ in pairs)
    values = "".join(f"<span class='value'>{value}</span>" for _, value in pairs)
    return (f"<div class='card-stats' style='grid-template-columns:repeat({len(pairs)}, auto)'>"
            f"{labels}{values}</div>")


def poster_card(film, key, caption_html, on_open, id_col="film_key"):
    """Poster with a caption beneath, in a keyed container; CSS stretches the button over all of it.

    Every poster is drawn the same way (one HTML block with its caption), so cards line up whatever
    they show. A film flagged `sensitive_poster` shows its title on a blurred poster instead; a film
    with no poster shows its title on a plain frame.
    """
    url    = poster_url(film.poster_path)
    hidden = blur_on() and bool(getattr(film, "sensitive_poster", False))
    title  = html.escape(film.film_title)

    if url and not hidden:
        frame = f"<div class='poster-frame'><img src='{url}' alt='{title}'></div>"
    else:
        img  = f"<img src='{url}' alt=''>" if url else ""
        note = "Poster hidden" if url else "No poster"
        frame = (f"<div class='poster-frame{' poster-hidden' if url else ''}'>{img}"
                 f"<div class='poster-label'><div class='poster-label-title'>{title}</div>"
                 f"<div class='poster-label-note'>{note}</div></div></div>")

    with st.container(key=key):
        st.markdown(frame + caption_html, unsafe_allow_html=True)
        st.button(film.film_title, key=f"open_{key}", on_click=on_open, args=(getattr(film, id_col),),
                  width="stretch")


def poster_grid(films, key_prefix, caption, on_open, id_col="film_key", per_row=6):
    """Rows of poster cards; `caption(film)` returns each card's HTML, `on_open(id)` runs on click."""
    for start in range(0, len(films), per_row):
        cols = st.columns(per_row)
        for i, (col, film) in enumerate(zip(cols, films.iloc[start:start + per_row].itertuples())):
            with col:
                poster_card(film, f"card_{key_prefix}_{start + i}", caption(film), on_open, id_col)


def excerpt(text, limit=220):
    """The start of a text, cut at a word boundary with an ellipsis if it runs past `limit` characters."""
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(",;:-") + "…"


# ---------- Shared card pieces ----------

FLAG_TEXT = {           # 05's out_of_range column names -> what a card says
    "genre":        "unfamiliar genre",
    "runtime":      "unusual runtime",
    "vote_average": "unusual crowd score",
    "film_year":    "unusual release year",
    "popularity":   "unusual popularity",
}


def runtime_text(minutes):
    """'2h 14m', or None when TMDB has no runtime."""
    if pd.isna(minutes) or minutes <= 0:
        return None
    h, m = divmod(int(minutes), 60)
    return f"{h}h {m}m" if h else f"{m}m"


def flag_html(out_of_range):
    """The ⚑ line for a card, or '' when the film is not flagged."""
    flags = out_of_range.split("|") if isinstance(out_of_range, str) and out_of_range else []
    if not flags:
        return ""
    return (f"<div style='color:var(--orange); font-size:0.8rem; margin-top:0.2rem'>⚑ "
            f"{' · '.join(FLAG_TEXT.get(f, f) for f in flags)}</div>")
