import streamlit as st

from src.app_data import RUNGS, load_tables
from src.app_ui import crowd, poster_url, stars, stars_exact

SHOWCASE_N = 12                   # rule fixed in advance: the most-voted test films, by vote_count alone

SCALE_LO, SCALE_HI = 0.5, 5.0

test = load_tables()["test"]

mae_model = (test["pred_deploy"] - test["rating"]).abs().mean()
mae_crowd = (test["pred_m1"] - test["rating"]).abs().mean()
showcase  = test.nlargest(SHOWCASE_N, "vote_count")


# ---------- Poster grid ----------

def open_film(film_key):
    st.session_state.open_film = film_key
    st.session_state.ladder_step = 1          # every film starts from "knows nothing"


def poster_card(film, key, caption_html):
    """Poster with a caption beneath, in a keyed container; CSS stretches the button over all of it."""
    with st.container(key=key):
        url = poster_url(film.poster_path)
        if url:
            st.image(url, width="stretch")
        else:
            st.markdown("<div style='aspect-ratio:2/3; background:var(--surface); "
                        "border-radius:6px'></div>", unsafe_allow_html=True)
        st.markdown(caption_html, unsafe_allow_html=True)
        st.button(film.film_title, key=f"open_{key}", on_click=open_film, args=(film.film_key,))


def poster_grid(films, key_prefix, caption, per_row=6):
    for start in range(0, len(films), per_row):
        cols = st.columns(per_row)
        for i, (col, film) in enumerate(zip(cols, films.iloc[start:start + per_row].itertuples())):
            with col:
                poster_card(film, f"card_{key_prefix}_{start + i}", caption(film))


def showcase_caption(film):
    return (f"<div class='card-meta'>{film.film_year}</div>"
            f"<div class='card-stats'>"
            f"<div><span class='label'>Predicted</span><span class='value'>{stars(film.pred_deploy)}</span></div>"
            f"<div><span class='label'>Rated</span><span class='value'>{stars(film.rating)}</span></div>"
            f"</div>")


# ---------- Model ladder ----------

def scale_pos(x):
    """Horizontal position on the ½★–5★ track, as a CSS number (percent)."""
    return (x - SCALE_LO) / (SCALE_HI - SCALE_LO) * 100


def ladder_html(film, step):
    """Rows up to `step` filled in (only the newest animates); later rows dimmed as a preview."""
    actual = f"<div class='actual' style='left:{scale_pos(film['rating']):.1f}%'></div>"
    rows = []

    for i, (col, label, sub, _) in enumerate(RUNGS):
        head = f"<div><div class='rung-label'>{label}</div><div class='rung-sub'>{sub}</div></div>"

        if i >= step:
            rows.append(f"<div class='rung pending'>{head}<div class='track'>{actual}</div>"
                        f"<div class='rung-value'>—</div></div>")
            continue

        x = film[col]
        track = actual
        detail = stars_exact(x)
        if i > 0:
            prev = film[RUNGS[i - 1][0]]
            lo, hi = sorted([scale_pos(prev), scale_pos(x)])
            track += (f"<div class='move' style='left:{lo:.1f}%; width:{hi - lo:.1f}%'></div>"
                      f"<div class='marker prev' style='left:{scale_pos(prev):.1f}%'></div>")
            change = x - prev
            detail += " · no change" if abs(change) < 0.005 else f" · {change:+.2f}".replace("-", "−")
        track += f"<div class='marker' style='left:{scale_pos(x):.1f}%'></div>"

        cls = "rung new" if i == step - 1 else "rung"
        rows.append(f"<div class='{cls}'>{head}<div class='track'>{track}</div>"
                    f"<div class='rung-value'>{stars(x)}<small>{detail}</small></div></div>")

    ticks = "".join(f"<span style='left:{scale_pos(s):.1f}%'>{s}★</span>" for s in [1, 2, 3, 4, 5])
    rows.append(f"<div class='rung scale'><div></div><div class='track-scale'>{ticks}</div><div></div></div>")
    return "".join(rows)


def film_dialog(film):
    @st.dialog(film["film_title"], width="large")
    def show():
        step = st.session_state.ladder_step

        url = poster_url(film["poster_path"])
        poster = f"<img class='ladder-poster' src='{url}'>" if url else ""
        html = (f"<div class='ladder-top'>{poster}<div class='ladder-head'>"
                f"{film['film_year']}<br>"
                f"Crowd score <b>{crowd(film['vote_average'])}</b> · "
                f"My rating <b>{stars(film['rating'])}</b></div></div>")

        html += ladder_html(film, step)
        if step == len(RUNGS):
            err_model = abs(film["pred_deploy"] - film["rating"])
            err_crowd = abs(film["pred_m1"] - film["rating"])
            html += (f"<div class='ladder-summary'>Final prediction <b>{stars(film['pred_deploy'])}</b>, "
                     f"off by <b>{err_model:.2f}&nbsp;★</b> — the crowd score alone was off by "
                     f"<b>{err_crowd:.2f}&nbsp;★</b>.</div>")
        html += ("<div class='ladder-note'><span style='color:var(--orange)'>●</span> prediction "
                 "&nbsp; <span style='color:var(--muted)'>●</span> previous layer "
                 "&nbsp; <span style='color:var(--green)'>┃</span> my rating &nbsp;·&nbsp; "
                 "The film details and history layers are the models as tested, which also used review "
                 "length; the final model doesn't, at no cost in accuracy.</div>")
        st.markdown(html, unsafe_allow_html=True)

        if step < len(RUNGS):
            st.button(f"{RUNGS[step][3]} →", type="primary", on_click=next_layer)
        else:
            st.button("Start again", on_click=restart_ladder)

    show()


def next_layer():
    st.session_state.ladder_step += 1


def restart_ladder():
    st.session_state.ladder_step = 1


# ---------- Page ----------

st.header("Beyond the crowd", anchor=False)

# "Nearly twice as well": Spearman 0.612 for the model against 0.340 for the crowd score (04 §15).
st.markdown(
    f"<p class='lead'>Tested on {len(test)} films it had never seen, the model's predictions were off by "
    f"<b>{mae_model:.2f}&nbsp;★</b> on average, against <b>{mae_crowd:.2f}&nbsp;★</b> for the crowd score — "
    f"and it ranked my films nearly twice as well.</p>"
    f"<p class='card-meta'>The {SHOWCASE_N} best-known films in the test set, by number of TMDB votes. "
    f"Open one to see how its prediction was built.</p>",
    unsafe_allow_html=True,
)

poster_grid(showcase, "showcase", showcase_caption)

opened = st.session_state.pop("open_film", None)
if opened is not None:
    film_dialog(test.loc[test["film_key"] == opened].iloc[0])