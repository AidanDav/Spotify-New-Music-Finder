import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

DB_PATH = "feedback.db"

# ---------------------------------------------------------------------------
# Database helpers for logging and retrieving user feedback on songs.
# ---------------------------------------------------------------------------
@contextmanager
def _connection():
    """One connection per call — feedback writes are infrequent (once per
    queued batch), so there's no real cost to opening fresh each time, and
    it sidesteps sharing a connection across the playback-polling thread
    we'll add later. sqlite3 connections aren't thread-safe by default;
    when that thread exists, it should go through this same helper rather
    than reuse a connection built on the main thread."""
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

# ---------------------------------------------------------------------------
# Feedback table schema and accessors
# ---------------------------------------------------------------------------
def init_db():
    """Creates the feedback table if it doesn't exist yet. Safe to call
    every startup — main.py should call this once before the main loop."""
    with _connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                song_name TEXT NOT NULL,
                artist_name TEXT NOT NULL,
                opinion TEXT NOT NULL CHECK (opinion IN ('liked', 'disliked')),
                source_type TEXT,
                created_at TEXT NOT NULL
            )
            """
        )

# ---------------------------------------------------------------------------
# Feedback logging and retrieval 
# ---------------------------------------------------------------------------
def log_feedback(song_name, artist_name, opinion, source_type=None):
    """
    Records one piece of feedback. Append-only — no upsert — so repeated
    feedback on the same song over time builds a history rather than
    overwriting.

    Args:
        song_name: track name
        artist_name: artist name
        opinion: "liked" or "disliked"
        source_type: where this song came from (e.g. "similar_songs",
                     "top_tracks") — optional, but useful later for
                     weighting recommendations by how the song surfaced
    """
    # Validate opinion before inserting into the database
    if opinion not in ("liked", "disliked"):
        raise ValueError(f"opinion must be 'liked' or 'disliked', got {opinion!r}")

    with _connection() as conn:
        conn.execute(
            """
            INSERT INTO feedback (song_name, artist_name, opinion, source_type, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (song_name, artist_name, opinion, source_type, datetime.now(timezone.utc).isoformat()),
        )

# ---------------------------------------------------------------------------
# Feedback retrieval and filtering
# ---------------------------------------------------------------------------
def get_feedback_for_artist(artist_name):
    """Returns all logged feedback rows for a given artist, most recent
    first. Each row: (song_name, opinion, source_type, created_at)."""
    with _connection() as conn:
        cursor = conn.execute(
            """
            SELECT song_name, opinion, source_type, created_at
            FROM feedback
            WHERE artist_name = ? COLLATE NOCASE
            ORDER BY created_at DESC
            """,
            (artist_name,),
        )
        return cursor.fetchall()

# ---------------------------------------------------------------------------
# Feedback filtering helpers
# ---------------------------------------------------------------------------
def get_recent_feedback(limit=20):
    """Returns the most recent feedback rows across all artists. Each row:
    (song_name, artist_name, opinion, source_type, created_at). Mainly
    useful for debugging/inspecting what's been logged."""
    with _connection() as conn:
        cursor = conn.execute(
            """
            SELECT song_name, artist_name, opinion, source_type, created_at
            FROM feedback
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return cursor.fetchall()

# ---------------------------------------------------------------------------
# Feedback filtering helpers for use in lastfm_client.py
# ---------------------------------------------------------------------------
def _get_current_opinions():
    """Shared helper: one row per (song, artist) pair reflecting only its
    MOST RECENT feedback entry. Both get_disliked_songs() and
    get_liked_songs() are just filters over this same underlying query, so
    a later opinion always overrides an earlier one consistently for both
    directions instead of each re-implementing the "most recent" logic
    separately."""
    # This is a bit of a SQL trick: we select all rows where the created_at \
    # timestamp is equal to the maximum created_at for that song/artist pair. This effectively gives us the 
    # most recent feedback entry for each unique song/artist combination.
    with _connection() as conn:
        cursor = conn.execute(
            """
            SELECT song_name, artist_name, opinion, created_at
            FROM feedback f
            WHERE created_at = (
                SELECT MAX(created_at) FROM feedback f2
                WHERE f2.song_name = f.song_name COLLATE NOCASE
                AND f2.artist_name = f.artist_name COLLATE NOCASE
            )
            ORDER BY created_at DESC
            """
        )
        return cursor.fetchall()

# ---------------------------------------------------------------------------
# Feedback filtering helpers for use in lastfm_client.py
# ---------------------------------------------------------------------------
def get_disliked_songs():
    """
    Returns a set of (song_name_lower, artist_name_lower) tuples for
    songs whose MOST RECENT feedback entry is 'disliked'.

    Uses the most recent entry per song/artist pair rather than "ever
    disliked" — so a later 'liked' entry on the same song overrides an
    earlier dislike instead of blacklisting it permanently.
    """
    rows = _get_current_opinions()
    return {
        (name.lower(), artist.lower())
        for name, artist, opinion, _ in rows
        if opinion == "disliked"
    }

# ---------------------------------------------------------------------------
# Feedback filtering helpers for use in lastfm_client.py
# ---------------------------------------------------------------------------
def get_liked_songs(limit=None):
    """
    Returns a list of {"name", "artist"} dicts for songs whose MOST RECENT
    feedback entry is 'liked' — the display-oriented mirror of
    get_disliked_songs(). Ordered most-recently-liked first.

    Unlike get_disliked_songs() (which returns a lookup set for
    filtering), this returns full song info, since it's meant to be shown
    to the user directly — e.g. when they ask the agent to see their
    liked songs.

    Uses the same most-recent-entry-wins logic as get_disliked_songs(), so
    a song that was liked and later disliked correctly drops off this
    list instead of lingering here permanently.
    """
    rows = _get_current_opinions()
    liked = [
        {"name": name, "artist": artist}
        for name, artist, opinion, _ in rows
        if opinion == "liked"
    ]
    return liked[:limit] if limit else liked

# ---------------------------------------------------------------------------
# Feedback filtering helpers for use in lastfm_client.py
# ---------------------------------------------------------------------------
def filter_disliked(tracks):
    """
    Removes tracks the user has most-recently disliked from a list.

    Args:
        tracks: list of dicts with 'name' and 'artist' keys (flat —
                not the nested Last.fm API shape)

    Returns:
        a new list, same shape, with disliked tracks removed. Order
        of the remaining tracks is preserved.
    """
    disliked = get_disliked_songs()
    if not disliked:
        return tracks
    return [
        t for t in tracks
        if (t["name"].lower(), t["artist"].lower()) not in disliked
    ]

# ---------------------------------------------------------------------------
# Feedback filtering helpers for use in lastfm_client.py
# ---------------------------------------------------------------------------
def filter_disliked_raw(tracks):
    """
    Same as filter_disliked, but for Last.fm's raw nested track shape
    (t['name'], t['artist']['name']) instead of the flat {'name','artist'}
    dicts used elsewhere. This lets lastfm_client.py filter out disliked
    songs BEFORE slicing to the final requested count, so a dislike
    doesn't shrink the result list — it gets backfilled from the
    over-fetched buffer instead.
    """
    disliked = get_disliked_songs()
    if not disliked:
        return tracks
    return [
        t for t in tracks
        if (t["name"].lower(), t["artist"]["name"].lower()) not in disliked
    ]

# ---------------------------------------------------------------------------
# Feedback filtering helpers for use in lastfm_client.py
# ---------------------------------------------------------------------------
def get_liked_artists():
    """Returns artist names with at least one 'liked' entry, along with
    a count, most-liked first. Useful later for steering recommendations
    toward artists the user has responded well to."""
    with _connection() as conn:
        cursor = conn.execute(
            """
            SELECT artist_name, COUNT(*) AS likes
            FROM feedback
            WHERE opinion = 'liked'
            GROUP BY artist_name COLLATE NOCASE
            ORDER BY likes DESC
            """
        )
        return cursor.fetchall()