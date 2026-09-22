import streamlit as st

from src.app_data import load_tables
from src.app_ui import crowd, poster_url, stars, stars_exact

SHOWCASE_N = 12                   # rule fixed in advance: the most-voted test films, by vote_count alone

RUNGS = [                         # (column, label, what the model knows at this rung)
    ("pred_m0",     "Knows nothing",  "My typical rating, same for every film"),
    ("pred_m1",     "+ Crowd score",  "TMDB's average rating"),
    ("pred_m2",     "+ Film details", "Genre, runtime, era, language"),
    ("pred_m3",     "+ My history",   "My past ratings of its director, genres, era"),
    ("pred_deploy", "+ Keywords",     "TMDB plot keywords — the final model"),
]
SCALE_LO, SCALE_HI = 0.5, 5.0

test = load_tables()["test"]

mae_model = (test["pred_deploy"] - test["rating"]).abs().mean()
mae_crowd = (test["pred_m1"] - test["rating"]).abs().mean()
showcase  = test.nlargest(SHOWCASE_N, "vote_count")


def open_film(film_key):
    st.session_state.open_film = film_key


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
            f"<div class='card-meta'>Predicted <b style='color:var(--white)'>{stars(film.pred_deploy)}</b>"
            f" · Rated <b style='color:var(--white)'>{stars(film.rating)}</b></div>")


def scale_pos(x):
    """Horizontal position on the ½★–5★ track, as a CSS percentage."""
    return f"{(x - SCALE_LO) / (SCALE_HI - SCALE_LO) * 100:.1f}%"


def ladder_html(film):
    """One row per rung: prediction as an orange dot, my rating as a green line through every row."""
    actual = scale_pos(film["rating"])
    rows = []
    for i, (col, label, sub) in enumerate(RUNGS):
        x = film[col]
        rows.append(
            f"<div class='rung' style='animation-delay:{i * 0.3:.1f}s'>"
            f"<div><div class='rung-label'>{label}</div><div class='rung-sub'>{sub}</div></div>"
            f"<div class='track'><div class='actual' style='left:{actual}'></div>"
            f"<div class='marker' style='left:{scale_pos(x)}'></div></div>"
            f"<div class='rung-value'>{stars(x)}<small>{stars_exact(x)}</small></div>"
            f"</div>"
        )
    ticks = "".join(f"<span style='left:{scale_pos(s)}'>{s}★</span>" for s in [1, 2, 3, 4, 5])
    rows.append(f"<div class='rung scale' style='animation-delay:{len(RUNGS) * 0.3:.1f}s'>"
                f"<div></div><div class='track-scale'>{ticks}</div><div></div></div>")
    return "".join(rows)


def film_dialog(film):
    @st.dialog(film.film_title, width="large")
    def show():
        left, right = st.columns([1, 4])
        with left:
            url = poster_url(film["poster_path"])
            if url:
                st.image(url, width="stretch")
        with right:
            st.markdown(
                f"<div class='ladder-head'>{film['film_year']}<br>"
                f"Crowd score <b>{crowd(film['vote_average'])}</b><br>"
                f"My rating <b>{stars(film['rating'])}</b> · "
                f"Final prediction <b>{stars(film['pred_deploy'])}</b></div>",
                unsafe_allow_html=True,
            )
        st.markdown(
            ladder_html(film)
            + "<div class='ladder-note'><span style='color:var(--orange)'>●</span> prediction as each layer "
              "is added &nbsp; <span style='color:var(--green)'>┃</span> my rating<br>"
              "The film details and history steps are the models as tested, which also used review length; "
              "the final model doesn't, at no cost in accuracy.</div>",
            unsafe_allow_html=True,
        )
    show()


st.header("Beyond the crowd")

# "Nearly twice as well": Spearman 0.612 for the model against 0.340 for the crowd score (04 §15).
st.markdown(
    f"<p class='lead'>Tested on {len(test)} films it had never seen, the model's predictions were off by "
    f"<b>{mae_model:.2f} ★</b> on average, against <b>{mae_crowd:.2f} ★</b> for the crowd score — "
    f"and it ranked my films nearly twice as well.</p>"
    f"<p class='card-meta'>The {SHOWCASE_N} best-known films in the test set, by number of TMDB votes. "
    f"Open one to see how its prediction was built.</p>",
    unsafe_allow_html=True,
)

poster_grid(showcase, "showcase", showcase_caption)

opened = st.session_state.pop("open_film", None)
if opened is not None:
    film_dialog(test.loc[test["film_key"] == opened].iloc[0])