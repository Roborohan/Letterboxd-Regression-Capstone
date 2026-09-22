import html

import pandas as pd
import streamlit as st

from src.app_data import current_tables, display_name, possessive
from src.app_ui import card_stats, flag_html, gap, poster_grid, poster_url, runtime_text, stars, stars_exact

WATCHLIST, POPULAR = "On the watchlist", "Popular UK releases"
BLURB = {
    WATCHLIST: "Unreleased films {whose} watchlist already has.",
    POPULAR:   "The most popular films opening in UK cinemas in the same window, watchlist or not.",
}
SOURCE = {WATCHLIST: "watchlist", POPULAR: "popular"}

tables   = current_tables()
coming   = tables["coming"]
summary  = tables["watchlist_summary"]
model    = tables["model_summary"]
name     = display_name(st.session_state["user"])
whose    = possessive(name)

recent   = summary["recent_mean"]


def open_coming_film(uri):
    st.session_state.cs_open = uri


def release_text(date):
    return f"{pd.Timestamp(date):%-d %b %Y}"


def coming_caption(film, rank, of):
    return (f"<div class='card-meta'>{release_text(film.release_shown)}"
            + (f" · {runtime_text(film.runtime)}" if runtime_text(film.runtime) else "") + "</div>"
            + card_stats([("Predicted", stars(film.pred)), ("Vs recent", gap(film.pred - recent))])
            + f"<div class='card-meta'>#{rank} of {of}</div>"
            + flag_html(film.out_of_range))


def coming_dialog(film):
    @st.dialog(film["film_title"], width="large", on_dismiss="rerun")
    def show():
        url = poster_url(film["poster_path"])
        if url and not film["sensitive_poster"]:
            thumb = f"<img class='ladder-poster' src='{url}'>"
        elif url:
            thumb = (f"<div class='poster-frame poster-hidden' style='width:84px; flex:none; margin:0'>"
                     f"<img src='{url}' alt=''></div>")
        else:
            thumb = ""
        facts = " · ".join(str(x) for x in [release_text(film["release_shown"]),
                                            runtime_text(film["runtime"]), film["director"]]
                           if pd.notna(x) and x)
        genres = film["genres"].replace("|", ", ") if isinstance(film["genres"], str) else ""
        st.markdown(f"<div class='ladder-top'>{thumb}<div class='ladder-head'>{html.escape(facts)}<br>"
                    f"{html.escape(genres)}</div></div>", unsafe_allow_html=True)

        st.markdown(
            card_stats([("Predicted", stars(film["pred"])),
                        ("Vs recent films", gap(film["pred"] - recent))])
            + f"<p class='card-meta' style='margin-top:0.6rem'>Unrounded prediction "
              f"{stars_exact(film['pred'])}, against {whose} recent-film average of "
              f"{stars_exact(recent)}. No crowd score exists yet, so this comes from the no-crowd "
              f"model, and there are no rated films to show behind it — the weights are only "
              f"computed for the watchlist.</p>",
            unsafe_allow_html=True,
        )

        notes = flag_html(film["out_of_range"])
        if notes:
            st.markdown(notes, unsafe_allow_html=True)

    show()


# ---------- Page ----------

st.header("Coming soon", anchor=False)

st.markdown(
    f"<p class='lead'>{len(coming)} films arriving in the 90 days after "
    f"{pd.Timestamp(summary['prediction_date']):%-d %B %Y}. None has a crowd score yet, so these use "
    f"the <b>no-crowd model</b> — {model['mae_nocrowd']:.2f}&nbsp;★ average error on the test set, "
    f"against {model['mae_deploy']:.2f}&nbsp;★ for the model used everywhere else.</p>"
    f"<p class='card-meta'>Predictions are shown against {whose} average of "
    f"<b style='color:var(--white)'>{stars_exact(recent)}</b> for films from "
    f"{int(summary['recent_from'])} onwards, since an absolute prediction means less without a crowd "
    f"score beside it. The spread is narrow — read these as roughly ordered, not as a table of "
    f"scores.</p>",
    unsafe_allow_html=True,
)

counts = coming["source"].value_counts()
labels = [f"{s} · {counts.get(SOURCE[s], 0)}" for s in (WATCHLIST, POPULAR)]
choice = st.segmented_control("Which films?", labels, default=labels[0], key="cs_mode",
                              label_visibility="collapsed") or labels[0]
section = WATCHLIST if choice == labels[0] else POPULAR

st.markdown(f"<p class='card-meta'>{BLURB[section].format(whose=whose)}</p>", unsafe_allow_html=True)

films = (coming[coming["source"] == SOURCE[section]]
         .sort_values("pred", ascending=False).reset_index(drop=True))
poster_grid(films, f"coming_{SOURCE[section]}",
            lambda f: coming_caption(f, f.Index + 1, len(films)), open_coming_film,
            id_col="film_uri")

left_out = summary["no_runtime_yet"]
if isinstance(left_out, str) and left_out:
    names = ", ".join(left_out.split("|"))
    st.markdown(f"<p class='card-meta' style='margin-top:1rem'>Left out because TMDB has no runtime for "
                f"them yet, which the model needs: {html.escape(names)}.</p>", unsafe_allow_html=True)

opened = st.session_state.pop("cs_open", None)
if opened is not None:
    coming_dialog(coming.loc[coming["film_uri"] == opened].iloc[0])
