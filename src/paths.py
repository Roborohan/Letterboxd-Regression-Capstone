"""Where each user's files live.

Every export gets its own working folder, data/interim/<username>/, and its own app folder,
data/processed/<username>/. The TMDB caches are shared: a film's TMDB record is the same
whoever watched it, so a second user's run reuses the cache instead of re-fetching.
"""

from pathlib import Path

ROOT      = Path(__file__).resolve().parent.parent
INTERIM   = ROOT / "data" / "interim"
PROCESSED = ROOT / "data" / "processed"
CACHE     = ROOT / "data" / "cache"
ACTIVE    = INTERIM / "active_user.txt"


def set_active_user(username):
    """Record whose export the later notebooks/scripts should read (written by 01)."""
    INTERIM.mkdir(parents=True, exist_ok=True)
    ACTIVE.write_text(username.strip() + "\n")
    return username.strip()


def active_user():
    """The username 01 last wrote, or an error telling you to run 01 first."""
    if not ACTIVE.exists():
        raise FileNotFoundError(
            f"No active user recorded at {ACTIVE}. Run 01_data_loading first — it writes this "
            "file from the export's profile."
        )
    return ACTIVE.read_text().strip()


def interim_dir(username=None):
    """data/interim/<username>/, created if needed."""
    folder = INTERIM / (username or active_user())
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def app_dir(username=None):
    """data/processed/<username>/, created if needed."""
    folder = PROCESSED / (username or active_user())
    folder.mkdir(parents=True, exist_ok=True)
    return folder

def require_user(expected):
    """The active user, but stop if it isn't the one this notebook is written for.

    The notebooks read and write whichever user ran last (01, or run_pipeline.py), so
    running them after a pipeline run on someone else's export would quietly work on
    their files. This makes that a stop rather than a surprise.
    """
    user = active_user()
    if user != expected:
        raise RuntimeError(
            f"Active user is '{user}', but this notebook is written for '{expected}'.\n"
            f"Run 01_data_loading on {expected}'s export first, or set it directly with:\n"
            f"    from src.paths import set_active_user; set_active_user('{expected}')\n"
            f"(run_pipeline.py sets the active user to whichever export it just processed.)"
        )
    print(f"active user: {user}")
    return user