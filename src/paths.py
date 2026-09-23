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